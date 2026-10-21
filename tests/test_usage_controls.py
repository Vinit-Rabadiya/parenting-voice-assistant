from unittest.mock import MagicMock

import pytest

from backend.api.dependencies import (
    get_caregiver_data_service, get_coaching_service, get_retrieval_service,
    get_usage_control_service,
)
from backend.core.security import require_authenticated_user
from backend.main import app
from backend.services.usage import UsageControlService, UsageDecision, next_usage


def test_hour_limit_and_reset_preserve_daily_count():
    _, record = next_usage({}, 100, 1, 10)
    decision, unchanged = next_usage(record, 100.2, 1, 10)
    assert decision == UsageDecision(False, 3500, "hourly")
    assert unchanged == record
    decision, updated = next_usage(record, 3600, 1, 10)
    assert decision.allowed
    assert updated["hour_count"] == 1
    assert updated["day_count"] == 2


def test_daily_limit_resets_at_nairobi_midnight():
    _, record = next_usage({}, 72000, 10, 1)
    decision, _ = next_usage(record, 75599.5, 10, 1)
    assert decision == UsageDecision(False, 1, "daily")
    decision, updated = next_usage(record, 75600, 10, 1)
    assert decision.allowed
    assert updated["day_count"] == 1


def test_both_limits_wait_until_both_are_available():
    _, record = next_usage({}, 100, 1, 1)
    decision, _ = next_usage(record, 101, 1, 1)
    assert decision == UsageDecision(False, 75499, "daily")


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_limits_are_rejected(limit):
    with pytest.raises(ValueError):
        next_usage({}, 100, limit, 10)


@pytest.mark.parametrize("record", [
    {"hour_bucket": 0},
    {"hour_bucket": 0, "hour_count": -1},
    {"hour_bucket": 1, "hour_count": 1},
])
def test_invalid_counter_is_not_silently_reset(record):
    with pytest.raises(ValueError):
        next_usage(record, 100, 10, 100)


def test_transaction_only_writes_accepted_reservations(monkeypatch):
    # Exercise the reservation callback without contacting Firestore.
    monkeypatch.setattr("backend.services.usage.firestore.transactional", lambda fn: fn)
    client = MagicMock()
    document = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    snapshot = document.get.return_value
    snapshot.exists = False
    service = UsageControlService(client, clock=lambda: 100)
    assert service.consume("account-1", "coaching", 1, 10).allowed
    transaction = client.transaction.return_value
    updated = transaction.set.call_args.args[1]
    document.get.assert_called_once_with(transaction=transaction)
    client.collection.return_value.document.assert_called_with("account-1")
    snapshot.exists = True
    snapshot.to_dict.return_value = updated
    transaction.set.reset_mock()
    assert not service.consume("account-1", "coaching", 1, 10).allowed
    transaction.set.assert_not_called()


def test_read_usage_does_not_write_and_normalizes_expired_windows():
    client = MagicMock()
    document = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    document.get.return_value.exists = True
    document.get.return_value.to_dict.return_value = {
        "hour_bucket": 0, "hour_count": 3, "day_bucket": 0, "day_count": 8,
    }
    result = UsageControlService(client, clock=lambda: 3600).read("account-1", {"coaching": (30, 100)})
    item = result["items"][0]
    assert item["hourly"]["used"] == 0
    assert item["daily"]["used"] == 8
    assert item["daily"]["remaining"] == 92
    assert item["daily"]["resets_at"].timestamp() == 75600
    client.collection.return_value.document.assert_called_with("account-1")
    document.set.assert_not_called()
    client.transaction.assert_not_called()


@pytest.fixture
def services(client):
    data, usage, retrieval, coaching = [MagicMock() for _ in range(4)]
    data.get_child.return_value = {"age_months": 6, "completed_months": 6,
                                   "age_days": 183, "in_scope": True}
    data.create_interaction.return_value = "interaction-1"
    usage.consume.return_value = UsageDecision(False, 60, "hourly")
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.update({
        require_authenticated_user: lambda: {"uid": "account-1"},
        get_caregiver_data_service: lambda: data,
        get_usage_control_service: lambda: usage,
        get_retrieval_service: lambda: retrieval,
        get_coaching_service: lambda: coaching,
    })
    yield data, usage, retrieval, coaching
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def test_coaching_limit_stops_retrieval_and_generation(client, services):
    _, usage, retrieval, coaching = services
    response = client.post("/coach", json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert usage.consume.call_args.args[:2] == ("account-1", "coaching")
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_usage_endpoint_reads_only_signed_in_account(client, services):
    _, usage, _, _ = services
    usage.read.return_value = {"items": [], "as_of": "2026-10-21T12:00:00Z"}
    response = client.get("/me/usage")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert usage.read.call_args.args[0] == "account-1"
    usage.consume.assert_not_called()


def test_usage_read_failure_returns_unavailable(client, services):
    _, usage, _, _ = services
    usage.read.side_effect = RuntimeError("private storage detail")
    response = client.get("/me/usage")
    assert response.status_code == 503
    assert "private storage detail" not in response.text


def test_usage_storage_failure_stops_processing(client, services):
    _, usage, retrieval, coaching = services
    usage.consume.side_effect = RuntimeError("unavailable")
    response = client.post("/coach", json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code == 503
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_missing_child_does_not_consume_quota(client, services):
    data, usage, _, _ = services
    data.get_child.return_value = None
    response = client.post("/coach", json={"child_id": "missing", "question": "Play ideas"})
    assert response.status_code == 404
    usage.consume.assert_not_called()


def test_child_creation_limit_prevents_new_profile(client, services):
    data, usage, _, _ = services
    response = client.post("/children", json={"name": "Baby", "date_of_birth": "2026-10-01"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert usage.consume.call_args.args[:2] == ("account-1", "child_creation")
    data.create_child.assert_not_called()


def test_safety_response_does_not_consume_quota(client, services):
    _, usage, retrieval, coaching = services
    response = client.post("/coach", json={"child_id": "child-1", "question": "My baby is not breathing"})
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
    usage.consume.assert_not_called()
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
