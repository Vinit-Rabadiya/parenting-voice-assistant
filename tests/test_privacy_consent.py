"""Consent policy tests use the real dependency, not the accepted-consent fixture."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request

from backend.api.consent import require_processing_consent
from backend.api.dependencies import get_caregiver_data_service
from backend.core.privacy import CONSENT_VERSION
from backend.core.security import require_authenticated_user
from backend.main import app
from backend.services.caregiver_data import CaregiverDataService


@pytest.fixture
def consent_api(client):
    overrides = app.dependency_overrides.copy()
    app.dependency_overrides.pop(require_processing_consent, None)
    service = MagicMock()
    service.get_consent.return_value = {}
    app.dependency_overrides[require_authenticated_user] = lambda: {"uid": "account-a"}
    app.dependency_overrides[get_caregiver_data_service] = lambda: service
    try:
        yield service
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)


def test_notice_does_not_assume_existing_accounts_accepted(client, consent_api):
    result = client.get("/privacy/consent")
    assert result.status_code == 200
    assert result.json()["accepted"] is False
    assert result.json()["accepted_at"] is None
    assert result.json()["notice"]
    consent_api.get_consent.assert_called_once_with("account-a")
    consent_api.save_consent.assert_not_called()


def test_acceptance_uses_authenticated_account_and_server_time(client, consent_api):
    now = datetime.now(timezone.utc)
    consent_api.save_consent.return_value = now
    response = client.post("/privacy/consent", json={"version": CONSENT_VERSION,
        "accepted": True, "caregiver_authority": True})
    assert response.status_code == 200
    assert response.json()["accepted"] is True
    consent_api.save_consent.assert_called_once_with("account-a", CONSENT_VERSION)


@pytest.mark.parametrize("changes,status", [
    ({"accepted": False}, 422), ({"caregiver_authority": False}, 422),
    ({"accepted": "true"}, 422), ({"version": "old"}, 409),
    ({"uid": "account-b"}, 422), ({"consent_at": "2026-01-01"}, 422),
])
def test_invalid_acceptance_never_writes(client, consent_api, changes, status):
    payload = {"version": CONSENT_VERSION, "accepted": True, "caregiver_authority": True, **changes}
    assert client.post("/privacy/consent", json=payload).status_code == status
    consent_api.save_consent.assert_not_called()


@pytest.mark.parametrize("method,path,payload", [
    ("POST", "/children", {"name": "Child", "date_of_birth": "2026-10-01"}),
    ("PATCH", "/children/child-1", {"name": "Changed"}),
    ("POST", "/conversations", {"child_id": "child-1"}),
    ("POST", "/coach", {"child_id": "child-1", "question": "Play ideas"}),
    ("POST", "/coach/message-1/feedback", {"helpful": True}),
    ("POST", "/speech/transcribe", None),
])
def test_new_processing_requires_consent(client, consent_api, method, path, payload):
    response = client.request(method, path, json=payload)
    assert response.status_code == 403
    assert response.headers["X-Consent-Required"] == "true"
    consent_api.create_child.assert_not_called()
    consent_api.update_child.assert_not_called()
    consent_api.create_conversation.assert_not_called()
    consent_api.get_child.assert_not_called()


@pytest.mark.parametrize("consent", [
    {"consent_version": "old", "consent_at": datetime.now(timezone.utc), "caregiver_authority": True},
    {"consent_version": CONSENT_VERSION, "consent_at": None, "caregiver_authority": True},
    {"consent_version": CONSENT_VERSION, "consent_at": datetime.now(timezone.utc)},
])
def test_old_or_incomplete_records_do_not_allow_processing(client, consent_api, consent):
    consent_api.get_consent.return_value = consent
    assert client.post("/conversations", json={"child_id": "child-1"}).status_code == 403


def test_current_consent_allows_endpoint_to_continue(client, consent_api):
    consent_api.get_consent.return_value = {"consent_version": CONSENT_VERSION,
        "consent_at": datetime.now(timezone.utc), "caregiver_authority": True}
    consent_api.create_conversation.return_value = None
    assert client.post("/conversations", json={"child_id": "missing"}).status_code == 404
    consent_api.create_conversation.assert_called_once_with("account-a", "missing")


def test_reads_and_deletion_remain_available_without_consent(client, consent_api):
    consent_api.list_children.return_value = []
    consent_api.delete_child.return_value = True
    consent_api.delete_conversation.return_value = True
    assert client.get("/children").status_code == 200
    assert client.delete("/children/child-1").status_code == 204
    assert client.delete("/conversations/chat-1").status_code == 204
    consent_api.get_consent.assert_not_called()


def test_account_deletion_does_not_require_consent(client, consent_api):
    import time

    def recent_login(request: Request):
        request.state.auth_time = time.time()
        return {"uid": "account-a"}

    app.dependency_overrides[require_authenticated_user] = recent_login
    with patch("backend.api.v1.endpoints.auth.auth.delete_user"):
        assert client.delete("/me").status_code == 204
    consent_api.delete_account_data.assert_called_once_with("account-a")
    consent_api.get_consent.assert_not_called()


def test_data_deletion_keeps_login_and_does_not_require_consent(client, consent_api):
    import time

    def recent_login(request: Request):
        request.state.auth_time = time.time()
        return {"uid": "account-a"}

    app.dependency_overrides[require_authenticated_user] = recent_login
    with patch("backend.api.v1.endpoints.auth.auth.delete_user") as delete_login:
        assert client.delete("/me/data").status_code == 204
        assert client.get("/me").status_code == 200
    consent_api.delete_account_data.assert_called_once_with("account-a")
    delete_login.assert_not_called()
    consent_api.get_consent.assert_not_called()


@pytest.mark.parametrize("path", ["/me/data", "/me"])
@pytest.mark.parametrize("auth_time", [None, 0, True, float("nan"), float("inf")])
def test_deletion_requires_valid_recent_sign_in(client, consent_api, path, auth_time):
    def invalid_login(request: Request):
        request.state.auth_time = auth_time
        return {"uid": "account-a"}

    app.dependency_overrides[require_authenticated_user] = invalid_login
    assert client.delete(path).status_code == 403
    consent_api.delete_account_data.assert_not_called()


def test_data_deletion_failure_returns_retryable_error_without_deleting_login(client, consent_api):
    import time

    def recent_login(request: Request):
        request.state.auth_time = time.time()
        return {"uid": "account-a"}

    app.dependency_overrides[require_authenticated_user] = recent_login
    consent_api.delete_account_data.side_effect = RuntimeError("PRIVATE_DETAILS")
    with patch("backend.api.v1.endpoints.auth.auth.delete_user") as delete_login:
        result = client.delete("/me/data")
    assert result.status_code == 503
    assert "PRIVATE_DETAILS" not in result.text
    delete_login.assert_not_called()


def test_data_deletion_requires_authentication(client):
    assert client.delete("/me/data").status_code == 401


def test_data_deletion_recursively_targets_only_the_authenticated_account():
    storage = MagicMock()
    CaregiverDataService(storage).delete_account_data("account-a")
    storage.collection.assert_called_once_with("users")
    storage.collection.return_value.document.assert_called_once_with("account-a")
    storage.recursive_delete.assert_called_once_with(storage.collection.return_value.document.return_value)


def test_storage_failure_blocks_new_processing(client, consent_api):
    consent_api.get_consent.side_effect = RuntimeError("PRIVATE_DETAILS")
    result = client.post("/conversations", json={"child_id": "child-1"})
    assert result.status_code == 503
    assert "PRIVATE_DETAILS" not in result.text
    consent_api.create_conversation.assert_not_called()


def test_consent_endpoints_require_authentication(client):
    assert client.get("/privacy/consent").status_code == 401
    assert client.post("/privacy/consent", json={}).status_code == 401


def test_acceptance_transaction_merges_and_preserves_existing_data():
    storage = MagicMock()
    document = storage.collection.return_value.document.return_value
    document.get.return_value.exists = False
    with patch("backend.services.caregiver_data.firestore.transactional", side_effect=lambda function: function):
        accepted_at = CaregiverDataService(storage).save_consent("account-a", CONSENT_VERSION)
    values = storage.transaction.return_value.set.call_args
    assert values.args[0] is document
    assert values.args[1] == {"consent_version": CONSENT_VERSION, "consent_at": accepted_at, "caregiver_authority": True}
    assert values.kwargs == {"merge": True}
    assert accepted_at.tzinfo is not None


def test_repeated_acceptance_preserves_original_timestamp():
    storage = MagicMock()
    document = storage.collection.return_value.document.return_value
    original = datetime(2026, 10, 21, tzinfo=timezone.utc)
    document.get.return_value.exists = True
    document.get.return_value.to_dict.return_value = {"consent_version": CONSENT_VERSION,
        "consent_at": original, "caregiver_authority": True}
    with patch("backend.services.caregiver_data.firestore.transactional", side_effect=lambda function: function):
        assert CaregiverDataService(storage).save_consent("account-a", CONSENT_VERSION) == original
    storage.transaction.return_value.set.assert_not_called()
