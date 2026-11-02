from datetime import date

import pytest

from backend.services.caregiver_data import baseline_milestones, calculate_age
from backend.services.age import add_months, age_details, within_project_scope
from unittest.mock import MagicMock
from pydantic import ValidationError

from backend.core.config import settings
from backend.schemas.children import ChildCreateRequest, ChildUpdateRequest
from backend.services.caregiver_data import CaregiverDataService


def test_calculate_age_returns_server_calculated_display_values():
    age_days, age_months, age_label = calculate_age(date(2026, 1, 18), today=date(2026, 10, 18))

    assert age_days == 273
    assert age_months == 9.0
    assert age_label == "9 months"


def test_calculate_age_rejects_future_date_of_birth():
    with pytest.raises(ValueError, match="future"):
        calculate_age(date(2026, 10, 19), today=date(2026, 10, 18))


def test_baseline_milestones_follow_the_calculated_age_band():
    milestones = baseline_milestones(6.0)

    assert "Sits without support" in milestones


def test_calendar_age_does_not_round_into_next_retrieval_band():
    days, months, display = age_details(date(2026, 1, 20), date(2026, 7, 19))
    assert days == 180
    assert months == 5
    assert display < 6
    assert age_details(date(2026, 1, 20), date(2026, 7, 20))[:2] == (181, 6)


def test_month_end_and_leap_year_birthdays():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert age_details(date(2026, 1, 31), date(2026, 2, 28))[1] == 1


@pytest.mark.parametrize("birthday,second_birthday", [
    (date(2024, 2, 29), date(2026, 2, 28)),
    (date(2023, 10, 20), date(2025, 10, 20)),
])
def test_project_scope_uses_calendar_second_birthday(birthday, second_birthday):
    from datetime import timedelta

    assert within_project_scope(birthday, birthday)
    assert within_project_scope(birthday, second_birthday)
    assert not within_project_scope(birthday, second_birthday + timedelta(days=1))
    with pytest.raises(ValueError, match="second birthday"):
        calculate_age(birthday, second_birthday + timedelta(days=1))


def test_aged_out_profile_remains_readable_without_milestone_guidance(monkeypatch):
    from unittest.mock import MagicMock
    from backend.services.caregiver_data import CaregiverDataService

    monkeypatch.setattr("backend.services.caregiver_data.current_date", lambda: date(2026, 10, 20))
    document = MagicMock()
    document.id = "child-1"
    document.to_dict.return_value = {"name": "Example", "date_of_birth": "2024-10-19"}
    profile = CaregiverDataService._child_response(document)
    assert profile["in_scope"] is False
    assert profile["baseline_milestones"] == []
    assert profile["age_days"] == 731


@pytest.fixture
def profile_storage(monkeypatch):
    monkeypatch.setattr("backend.services.caregiver_data.current_date", lambda: date(2026, 10, 20))
    monkeypatch.setattr(settings, "GEMINI_PAID_SERVICES_CONFIRMED", False)
    monkeypatch.setattr(settings, "GEMINI_NONPERSONAL_TESTING_CONFIRMED", False)
    database = MagicMock()
    service = CaregiverDataService(database)
    document = service._children("account-a").document.return_value
    document.id = "child-1"
    document.get.return_value.exists = True
    document.get.return_value.id = "child-1"
    document.get.return_value.to_dict.return_value = {"name": "Example", "date_of_birth": "2026-04-20"}
    return service, document, database


def test_health_notes_are_private_profile_fields_and_default_to_not_shared(profile_storage):
    service, document, _ = profile_storage
    service.create_child("account-a", "Example", date(2026, 4, 20), None,
                         health_details={"allergies": " Example allergy "})
    stored = document.set.call_args.args[0]
    assert stored["health_details"]["allergies"] == "Example allergy"
    assert stored["use_health_details"] is False
    assert service.get_child("account-a", "child-1")["health_context_available"] is False


def test_health_note_edits_and_clear_do_not_replace_other_profile_fields(profile_storage):
    service, document, _ = profile_storage
    service.update_child("account-a", "child-1", {"health_details": {"history": "Review note"}})
    stored = document.update.call_args.args[0]
    assert set(stored) == {"health_details", "health_context_revision"}
    assert stored["health_details"]["history"] == "Review note"
    service.update_child("account-a", "child-1", {"health_details": None})
    assert all(value == "" for value in document.update.call_args.args[0]["health_details"].values())
    assert document.update.call_args.args[0]["health_context_revision"] != stored["health_context_revision"]


def test_legacy_profiles_return_empty_health_notes_without_a_migration(profile_storage):
    service, _, _ = profile_storage
    result = service.get_child("account-a", "child-1")
    assert result["health_details"] == {}
    assert result["use_health_details"] is False


def test_unconfirmed_configuration_cannot_enable_health_sharing_at_storage_boundary(profile_storage):
    service, document, _ = profile_storage
    with pytest.raises(ValueError, match="currently unavailable"):
        service.create_child("account-a", "Example", date(2026, 4, 20), None, use_health_details=True)
    document.set.assert_not_called()
    with pytest.raises(ValueError, match="currently unavailable"):
        service.update_child("account-a", "child-1", {"use_health_details": True})
    document.update.assert_not_called()


def test_confirmed_testing_allows_notes_in_replies_without_paid_confirmation(profile_storage, monkeypatch):
    service, document, _ = profile_storage
    monkeypatch.setattr(settings, "GEMINI_NONPERSONAL_TESTING_CONFIRMED", True)
    service.update_child("account-a", "child-1", {"health_details": {"allergies": "Example note"},
                                                "use_health_details": True})
    values = document.update.call_args.args[0]
    assert values["health_details"]["allergies"] == "Example note"
    assert values["use_health_details"] is True
    assert service.get_child("account-a", "child-1")["health_context_available"] is True
    assert settings.GEMINI_PAID_SERVICES_CONFIRMED is False


def test_health_sharing_can_be_enabled_and_revoked_when_available(profile_storage, monkeypatch):
    service, document, _ = profile_storage
    monkeypatch.setattr(settings, "GEMINI_PAID_SERVICES_CONFIRMED", True)
    service.update_child("account-a", "child-1", {"use_health_details": True})
    assert document.update.call_args.args[0]["use_health_details"] is True
    monkeypatch.setattr(settings, "GEMINI_PAID_SERVICES_CONFIRMED", False)
    service.update_child("account-a", "child-1", {"use_health_details": False})
    assert document.update.call_args.args[0]["use_health_details"] is False


@pytest.mark.parametrize("health", [{"history": "x" * 601}, {"unknown_field": "value"}, {"allergies": ["value"]}])
def test_health_notes_have_a_bounded_known_schema(health):
    with pytest.raises(ValidationError):
        ChildCreateRequest(name="Example", date_of_birth=date(2026, 4, 20), health_details=health)


def test_partial_updates_preserve_omitted_notes_and_reject_string_sharing_flags():
    assert "health_details" not in ChildUpdateRequest(name="Changed").model_dump(exclude_unset=True)
    with pytest.raises(ValidationError):
        ChildUpdateRequest(use_health_details="false")


def test_profile_health_notes_follow_existing_recursive_child_deletion(profile_storage):
    service, child, database = profile_storage
    service._interactions("account-a").where.return_value.stream.return_value = []
    service._conversations("account-a").where.return_value.stream.return_value = []
    assert service.delete_child("account-a", "child-1") is True
    assert child in [call.args[0] for call in database.recursive_delete.call_args_list]


def test_child_api_connects_validated_health_fields_to_authenticated_storage(client):
    from backend.api.dependencies import get_caregiver_data_service
    from backend.core.security import require_authenticated_user
    from backend.main import app

    service = MagicMock()
    service.create_child.return_value = {
        "id": "child-1", "name": "Example", "date_of_birth": "2026-04-20", "age_months": 6,
        "age_days": 183, "completed_months": 6, "in_scope": True, "age_label": "6 months",
        "baseline_milestones": [], "health_details": {"allergies": "Example note"},
    }
    overrides = app.dependency_overrides.copy()
    app.dependency_overrides[require_authenticated_user] = lambda: {"uid": "account-a"}
    app.dependency_overrides[get_caregiver_data_service] = lambda: service
    try:
        response = client.post("/children", json={
            "name": "Example", "date_of_birth": "2026-04-20", "uid": "account-b",
            "health_details": {"allergies": "Example note"},
        })
        assert response.status_code == 201
        assert response.json()["health_details"]["allergies"] == "Example note"
        assert response.json()["use_health_details"] is False
        args = service.create_child.call_args
        assert args.args[0] == "account-a"
        assert args.kwargs["health_details"]["allergies"] == "Example note"
        assert args.kwargs["use_health_details"] is False
        service.update_child.return_value = service.create_child.return_value
        response = client.patch("/children/child-1", json={"health_details": None})
        assert response.status_code == 200
        service.update_child.assert_called_once_with("account-a", "child-1", {"health_details": None})
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)
