"""Both account-route aliases reject requests without a login token."""
import pytest
import json
import time
from unittest.mock import Mock, patch

from backend.core.security import get_account_security_service
from backend.services.account_security import AccountSecurityService
from scripts.reset_account_mfa import main as reset_mfa


@pytest.mark.parametrize("path", ["/me", "/api/v1/me", "/me/startup", "/api/v1/me/startup"])
def test_me_without_token_returns_401(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.json()["detail"] == "Login required."


def verified_claims(**extra):
    return {"uid": "caregiver", "email_verified": True, "auth_time": time.time(),
            "firebase": {"sign_in_provider": "google.com"}, **extra}


@pytest.fixture
def startup_data(client, monkeypatch):
    from datetime import datetime, timezone
    from backend.api.dependencies import get_caregiver_data_service
    from backend.core.privacy import CONSENT_VERSION

    data = Mock()
    data.get_consent.return_value = {"consent_version": CONSENT_VERSION,
        "consent_at": datetime.now(timezone.utc), "caregiver_authority": True}
    data.list_children.return_value = []
    monkeypatch.setitem(client.app.dependency_overrides, get_caregiver_data_service, lambda: data)
    return data


def test_startup_returns_owned_consent_and_profiles_after_one_revocation_check(client, startup_data):
    with patch("backend.core.security.auth.verify_id_token", return_value=verified_claims()) as verify:
        response = client.get("/me/startup", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json()["uid"] == "caregiver"
    assert response.json()["consent"]["accepted"] is True
    assert response.json()["children"] == []
    assert response.headers["cache-control"] == "no-store"
    startup_data.get_consent.assert_called_once_with("caregiver")
    startup_data.list_children.assert_called_once_with("caregiver")
    assert verify.call_count == 1 and verify.call_args.kwargs["check_revoked"] is True


def test_startup_does_not_return_profiles_without_current_consent(client, startup_data):
    startup_data.get_consent.return_value = {"consent_version": "old"}
    startup_data.list_children.return_value = [{"name": "PRIVATE_CHILD"}]
    with patch("backend.core.security.auth.verify_id_token", return_value=verified_claims()):
        response = client.get("/me/startup", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json()["consent"]["accepted"] is False
    assert "children" not in response.json()
    assert "PRIVATE_CHILD" not in response.text


def test_startup_keeps_mfa_enforcement_before_any_profile_read(client, startup_data):
    security = client.app.dependency_overrides[get_account_security_service]()
    security.read.return_value = {"mfa_enabled": True, "mfa_required": False}
    with patch("backend.core.security.auth.verify_id_token", return_value=verified_claims()):
        response = client.get("/me/startup", headers={"Authorization": "Bearer token"})
    assert response.status_code == 403
    startup_data.get_consent.assert_not_called()
    startup_data.list_children.assert_not_called()


def test_administrator_startup_never_reads_caregiver_data(client, startup_data):
    security = client.app.dependency_overrides[get_account_security_service]()
    security.read.return_value = {"mfa_enabled": True, "mfa_required": True, "feedback_summary_admin": True}
    claims = verified_claims(feedback_summary_admin=True, firebase={"sign_in_second_factor": "totp"})
    with patch("backend.core.security.auth.verify_id_token", return_value=claims):
        response = client.get("/me/startup", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json() == {"uid": "caregiver", "role": "administrator"}
    startup_data.get_consent.assert_not_called()
    startup_data.list_children.assert_not_called()


def test_startup_storage_error_does_not_return_partial_private_data(client, startup_data):
    startup_data.get_consent.side_effect = RuntimeError("PRIVATE_STORAGE_DETAILS")
    with patch("backend.core.security.auth.verify_id_token", return_value=verified_claims()):
        response = client.get("/me/startup", headers={"Authorization": "Bearer token"})
    assert response.status_code == 503
    assert "PRIVATE_STORAGE_DETAILS" not in response.text


@pytest.mark.parametrize("provider", ["google.com", "password"])
def test_verified_accounts_without_mfa_can_access_their_account(client, provider):
    with patch("backend.core.security.auth.verify_id_token", return_value=verified_claims(firebase={"sign_in_provider": provider})) as verify:
        response = client.get("/me", headers={"Authorization": "Bearer verified-token"})
    assert response.status_code == 200
    assert response.json() == {"uid": "caregiver", "role": "caregiver"}
    assert verify.call_args.kwargs["check_revoked"] is True


def test_google_provider_name_does_not_replace_verified_email(client):
    with patch("backend.core.security.auth.verify_id_token", return_value=verified_claims(email_verified=False)):
        assert client.get("/me", headers={"Authorization": "Bearer token"}).status_code == 403


@pytest.mark.parametrize("enabled,required", [(True, False), (False, True), (True, True)])
def test_enrolled_or_mandatory_accounts_cannot_use_first_factor_only_tokens(client, enabled, required):
    service = client.app.dependency_overrides[get_account_security_service]()
    service.read.return_value = {"mfa_enabled": enabled, "mfa_required": required}
    with patch("backend.core.security.auth.verify_id_token", return_value=verified_claims()):
        assert client.get("/me", headers={"Authorization": "Bearer token"}).status_code == 403
        status = client.get("/me/security", headers={"Authorization": "Bearer token"})
    assert status.status_code == 200
    assert status.json()["mfa_required"] is required
    assert status.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("required", [False, True])
def test_disabling_mfa_requires_recent_full_sign_in_and_respects_policy(client, required):
    service = client.app.dependency_overrides[get_account_security_service]()
    service.read.return_value = {"mfa_enabled": True, "mfa_required": required}
    claims = verified_claims(firebase={"sign_in_second_factor": "totp"})
    with patch("backend.core.security.auth.verify_id_token", return_value=claims):
        response = client.post("/me/security/mfa/disable?recovery=true", headers={"Authorization": "Bearer token"},
                               json={"mfa_required": False, "uid": "someone-else"})
    assert response.status_code == (403 if required else 204)
    if required:
        service.disable_mfa.assert_not_called()
    else:
        service.disable_mfa.assert_called_once_with("caregiver")


def test_old_sign_in_cannot_disable_mfa(client):
    service = client.app.dependency_overrides[get_account_security_service]()
    service.read.return_value = {"mfa_enabled": True, "mfa_required": False}
    with patch("backend.core.security.auth.verify_id_token", return_value=verified_claims(
            firebase={"sign_in_second_factor": "totp"}, auth_time=time.time() - 600)):
        assert client.post("/me/security/mfa/disable", headers={"Authorization": "Bearer token"}).status_code == 403
    service.disable_mfa.assert_not_called()


def test_mandatory_account_without_enrollment_cannot_reuse_old_mfa_claim(client):
    service = client.app.dependency_overrides[get_account_security_service]()
    service.read.return_value = {"mfa_enabled": False, "mfa_required": True}
    with patch("backend.core.security.auth.verify_id_token", return_value=verified_claims(
            firebase={"sign_in_second_factor": "totp"})):
        assert client.get("/me", headers={"Authorization": "Bearer token"}).status_code == 403
        assert client.get("/me/security", headers={"Authorization": "Bearer token"}).status_code == 200


def test_security_lookup_failure_does_not_grant_access(client):
    service = client.app.dependency_overrides[get_account_security_service]()
    service.read.side_effect = RuntimeError("PRIVATE")
    with patch("backend.core.security.auth.verify_id_token", return_value=verified_claims()):
        response = client.get("/me", headers={"Authorization": "Bearer token"})
    assert response.status_code == 503
    assert "PRIVATE" not in response.text


@pytest.mark.parametrize("global_required,claims,required", [
    (False, {}, False), (True, {}, True), (False, {"mfa_required": True}, True),
    (False, {"feedback_summary_admin": True}, True),
])
def test_provider_policy_is_authoritative_and_recovery_preserves_it(monkeypatch, global_required, claims, required):
    monkeypatch.setattr("backend.core.config.settings.AUTH_REQUIRE_MFA", global_required)
    service = AccountSecurityService(Mock())
    service._post = Mock(return_value={"users": [{"localId": "caregiver", "emailVerified": True,
                                                "mfaInfo": [{"totpInfo": {}}],
                                                "customAttributes": json.dumps(claims)}]})
    assert service.read("caregiver")["mfa_required"] is required
    if required:
        with pytest.raises(PermissionError):
            service.disable_mfa("caregiver")
        assert all(call.args[0] == "lookup" for call in service._post.call_args_list)
    service.disable_mfa("caregiver", recovery=True)
    action, payload = service._post.call_args.args
    assert action == "update"
    assert payload["localId"] == "caregiver"
    assert payload["mfa"] == {"enrollments": []}
    assert "validSince" in payload
    assert "customAttributes" not in payload


def test_recovery_preview_and_identity_check_never_change_accounts():
    with patch("scripts.reset_account_mfa.initialize_firebase") as initialize:
        reset_mfa(["--uid", "example"])
        with pytest.raises(SystemExit):
            reset_mfa(["--uid", "example", "--apply"])
    initialize.assert_not_called()


def test_provider_requests_use_admin_credentials_and_only_change_mfa_and_session_state(monkeypatch):
    monkeypatch.setattr("backend.core.config.settings.AUTH_REQUIRE_MFA", False)
    app = Mock(project_id="test-project")
    lookup, update = Mock(), Mock()
    lookup.json.return_value = {"users": [{"localId": "caregiver", "emailVerified": True, "mfaInfo": [{"totpInfo": {}}]}]}
    update.json.return_value = {}
    session = Mock()
    session.post.side_effect = [lookup, update]
    with patch("backend.services.account_security.AuthorizedSession", return_value=session) as factory:
        AccountSecurityService(app).disable_mfa("caregiver")
    factory.assert_called_with(app.credential.get_credential())
    assert session.post.call_args.args[0] == "https://identitytoolkit.googleapis.com/v1/projects/test-project/accounts:update"
    assert set(session.post.call_args.kwargs["json"]) == {"localId", "mfa", "validSince"}
    assert session.post.call_args.kwargs["timeout"] == 10
    assert session.close.call_count == 2
