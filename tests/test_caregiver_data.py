from datetime import date

import pytest

from backend.services.caregiver_data import baseline_milestones, calculate_age
from backend.services.age import add_months, age_details, within_project_scope


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
