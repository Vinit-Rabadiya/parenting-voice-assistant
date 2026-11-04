"""Session reuse removes remote checks without bypassing JWT or sensitive access checks."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import time
from unittest.mock import Mock, patch

from fastapi import Request
from firebase_admin import auth
import pytest

from backend.core.config import Settings
from backend.core.security import can_reuse_session, get_account_security_service
from backend.services.auth_sessions import AuthSessionCache


@pytest.fixture
def session_context(client, monkeypatch):
    clock = SimpleNamespace(tick=100.0, wall=time.time())
    cache = AuthSessionCache(clock=lambda: clock.tick, wall_clock=lambda: clock.wall)
    client.app.state.auth_session_cache = cache
    security = client.app.dependency_overrides[get_account_security_service]()
    claims = {"uid": "caregiver", "email_verified": True, "exp": clock.wall + 3600,
              "auth_time": clock.wall, "firebase": {"sign_in_provider": "password"}}
    monkeypatch.setattr("backend.core.config.settings.AUTH_REQUIRE_MFA", False)
    with patch("backend.core.security.auth.verify_id_token", return_value=claims) as verify:
        yield SimpleNamespace(client=client, clock=clock, cache=cache, security=security,
                              claims=claims, verify=verify, headers={"Authorization": "Bearer test-token"})


def revocation_checks(context):
    return [call.kwargs["check_revoked"] for call in context.verify.call_args_list]


def test_repeat_request_validates_jwt_but_reuses_remote_checks(session_context):
    c = session_context
    for path in ("/me", "/api/v1/me"):
        response = c.client.get(path, headers=c.headers)
        assert response.status_code == 200
        assert response.json() == {"uid": "caregiver", "role": "caregiver"}
        assert response.headers["cache-control"] == "no-store"
    assert revocation_checks(c) == [True, False]
    c.security.read.assert_called_once_with("caregiver")
    assert c.client.get("/me").status_code == 401


def test_cache_hits_do_not_extend_freshness_and_revocation_is_checked_after_ttl(session_context):
    c = session_context
    assert c.client.get("/me", headers=c.headers).status_code == 200
    c.clock.tick += 59
    assert c.client.get("/me", headers=c.headers).status_code == 200
    c.clock.tick += 1
    c.verify.side_effect = auth.RevokedIdTokenError("revoked")
    assert c.client.get("/me", headers=c.headers).status_code == 401
    assert revocation_checks(c) == [True, False, True]
    assert c.cache.get(c.cache.token_key("test-token")) is None


def test_cache_cannot_outlive_token_expiry(session_context):
    c = session_context
    c.claims["exp"] = c.clock.wall + 2
    assert c.client.get("/me", headers=c.headers).status_code == 200
    c.clock.wall += 2
    c.verify.side_effect = auth.ExpiredIdTokenError("expired", cause=None)
    assert c.client.get("/me", headers=c.headers).status_code == 401
    assert revocation_checks(c) == [True, True]


def test_expiry_during_jwt_verification_requires_fresh_remote_check(session_context):
    c = session_context
    assert c.client.get("/me", headers=c.headers).status_code == 200

    def verify(*args, check_revoked, **kwargs):
        if not check_revoked:
            c.clock.tick += 60
            return c.claims
        raise auth.RevokedIdTokenError("revoked during verification")

    c.verify.side_effect = verify
    assert c.client.get("/me", headers=c.headers).status_code == 401
    assert revocation_checks(c) == [True, False, True]


@pytest.mark.parametrize("changes", [
    {"email_verified": False}, {"firebase": {"tenant": "other"}},
])
def test_denied_claims_never_populate_session_cache(session_context, changes):
    c = session_context
    c.claims.update(changes)
    for _ in range(2):
        assert c.client.get("/me", headers=c.headers).status_code == 403
    assert revocation_checks(c) == [True, True]
    c.security.read.assert_not_called()


@pytest.mark.parametrize("state", [
    {"mfa_enabled": True, "mfa_required": False},
    {"mfa_enabled": False, "mfa_required": True},
])
def test_incomplete_mfa_never_populates_session_cache(session_context, state):
    c = session_context
    c.security.read.return_value = state
    for _ in range(2):
        assert c.client.get("/me", headers=c.headers).status_code == 403
    assert revocation_checks(c) == [True, True]
    assert c.security.read.call_count == 2


def test_completed_mfa_can_reuse_session(session_context):
    c = session_context
    c.security.read.return_value = {"mfa_enabled": True, "mfa_required": True}
    c.claims["firebase"]["sign_in_second_factor"] = "totp"
    for _ in range(2):
        assert c.client.get("/me", headers=c.headers).status_code == 200
    assert revocation_checks(c) == [True, False]
    c.security.read.assert_called_once()


def test_global_mfa_policy_is_enforced_even_on_cached_session(session_context, monkeypatch):
    c = session_context
    assert c.client.get("/me", headers=c.headers).status_code == 200
    monkeypatch.setattr("backend.core.config.settings.AUTH_REQUIRE_MFA", True)
    assert c.client.get("/me", headers=c.headers).status_code == 403


def test_new_token_and_other_accounts_require_remote_checks(session_context):
    c = session_context
    assert c.client.get("/me", headers=c.headers).status_code == 200
    assert c.client.get("/me", headers={"Authorization": "Bearer refreshed-token"}).status_code == 200
    c.claims = {**c.claims, "uid": "another-caregiver"}
    c.verify.return_value = c.claims
    for _ in range(2):
        response = c.client.get("/me", headers={"Authorization": "Bearer other-account-token"})
        assert response.status_code == 200
        assert response.json()["uid"] == "another-caregiver"
    assert revocation_checks(c) == [True, True, True, False]
    assert [call.args[0] for call in c.security.read.call_args_list] == ["caregiver", "caregiver", "another-caregiver"]


def test_cached_session_never_substitutes_for_valid_signature(session_context):
    c = session_context
    assert c.client.get("/me", headers=c.headers).status_code == 200
    c.verify.side_effect = auth.InvalidIdTokenError("bad signature")
    assert c.client.get("/me", headers=c.headers).status_code == 401
    assert c.cache.get(c.cache.token_key("test-token")) is None


def test_security_read_refreshes_policy_and_invalidates_all_user_tokens(session_context):
    c = session_context
    assert c.client.get("/me", headers=c.headers).status_code == 200
    c.security.read.return_value = {"mfa_enabled": False, "mfa_required": True}
    assert c.client.get("/api/v1/me/security", headers=c.headers).status_code == 200
    assert c.client.get("/me", headers=c.headers).status_code == 403
    assert revocation_checks(c) == [True, True, True]
    assert c.security.read.call_count == 3


@pytest.mark.parametrize("exception,status", [(PermissionError("disabled"), 403), (RuntimeError("offline"), 503)])
def test_failed_fresh_security_read_invalidates_cached_access(session_context, exception, status):
    c = session_context
    assert c.client.get("/me", headers=c.headers).status_code == 200
    c.security.read.side_effect = exception
    assert c.client.get("/me/security", headers=c.headers).status_code == status
    assert c.client.get("/me", headers=c.headers).status_code == status
    assert revocation_checks(c) == [True, True, True]


@pytest.mark.parametrize("token_admin,live_admin", [(True, True), (True, False), (False, True)])
def test_administrator_tokens_or_live_roles_are_never_cached(session_context, token_admin, live_admin):
    c = session_context
    c.claims["feedback_summary_admin"] = token_admin
    c.claims["firebase"]["sign_in_second_factor"] = "totp"
    c.security.read.return_value = {"mfa_enabled": True, "mfa_required": True, "feedback_summary_admin": live_admin}
    for _ in range(2):
        assert c.client.get("/me", headers=c.headers).status_code == 200
    assert revocation_checks(c) == [True, True]
    assert c.security.read.call_count == 2


def test_caregiver_cache_does_not_authorize_admin_endpoint(session_context):
    c = session_context
    assert c.client.get("/me", headers=c.headers).status_code == 200
    assert c.client.get("/admin/feedback/summary", headers=c.headers).status_code == 403
    assert revocation_checks(c) == [True, True]
    assert c.security.read.call_count == 2


def test_zero_ttl_disables_reuse_and_missing_cache_falls_back_to_fresh_checks(session_context):
    c = session_context
    c.client.app.state.auth_session_cache = AuthSessionCache(0)
    for _ in range(2):
        assert c.client.get("/me", headers=c.headers).status_code == 200
    del c.client.app.state.auth_session_cache
    assert c.client.get("/me", headers=c.headers).status_code == 200
    assert revocation_checks(c) == [True, True, True]


@pytest.mark.parametrize("method,path,reusable", [
    ("POST", "/coach", True), ("POST", "/api/v1/coach", True),
    ("POST", "/speech/transcribe", True), ("GET", "/conversations/thread", True),
    ("POST", "/coach/interaction/feedback", True), ("GET", "/privacy/consent", True),
    ("GET", "/me/security", False), ("POST", "/me/security/mfa/disable", False),
    ("GET", "/admin/feedback/summary", False), ("GET", "/api/v1/admin/feedback/access", False),
    ("DELETE", "/me", False), ("DELETE", "/me/data", False),
    ("DELETE", "/children/child", False), ("PATCH", "/children/child", False),
    ("DELETE", "/conversations/thread", False), ("GET", "/new-protected-feature", False),
])
def test_only_ordinary_caregiver_routes_can_reuse_remote_checks(method, path, reusable):
    request = Request({"type": "http", "method": method, "path": path, "headers": []})
    assert can_reuse_session(request) is reusable


def test_cache_bounds_privacy_invalidation_and_lifecycle():
    cache = AuthSessionCache(capacity=2, clock=lambda: 10, wall_clock=lambda: 100)
    security = {"mfa_enabled": False, "mfa_required": False, "private": "PRIVATE_DATA"}

    def remember(token, uid="caregiver", revision=0):
        cache.remember(cache.token_key(token), {"uid": uid, "exp": 200, "email": "PRIVATE_EMAIL"},
                       security, started=10, revision=revision)

    remember("secret-token-one")
    remember("secret-token-two", "another")
    key = cache.token_key("secret-token-one")
    cache.get(key).security["mfa_required"] = True
    assert cache.get(key).security["mfa_required"] is False
    remember("secret-token-three", "third")
    assert cache.get(cache.token_key("secret-token-two")) is None
    assert len(cache._entries) == 2
    assert "secret-token" not in repr(cache._entries)
    assert "PRIVATE" not in repr(cache._entries)
    revision = cache.invalidate_user("caregiver")
    assert cache.get(key) is None
    assert cache.get(cache.token_key("secret-token-three")) is not None
    remember("stale-in-flight", revision=revision - 1)
    assert cache.get(cache.token_key("stale-in-flight")) is None
    remember("new-valid-token", revision=revision)
    assert cache.get(cache.token_key("new-valid-token")) is not None
    cache.close()
    cache.close()
    remember("after-close", revision=revision)
    assert not cache._entries


def test_concurrent_cache_access_stays_bounded_and_isolated():
    cache = AuthSessionCache(capacity=8, clock=lambda: 10, wall_clock=lambda: 100)

    def access(index):
        key = cache.token_key(f"token-{index}")
        cache.remember(key, {"uid": f"user-{index}", "exp": 200}, {}, started=10, revision=0)
        entry = cache.get(key)
        assert entry is None or entry.uid == f"user-{index}"

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(access, range(80)))
    assert len(cache._entries) <= 8


@pytest.mark.parametrize("expiry", [None, True, "200", float("nan"), float("inf"), 100])
def test_missing_invalid_or_expired_token_expiry_cannot_be_cached(expiry):
    cache = AuthSessionCache(clock=lambda: 10, wall_clock=lambda: 100)
    key = cache.token_key("token")
    cache.remember(key, {"uid": "caregiver", "exp": expiry}, {}, started=10, revision=0)
    assert cache.get(key) is None


@pytest.mark.parametrize("ttl", [-1, 18001, True, float("nan"), "60"])
def test_invalid_ttl_is_rejected_before_firebase_initialization(ttl):
    settings = Settings()
    settings.AUTH_SESSION_CACHE_TTL_SECONDS = ttl
    with pytest.raises(ValueError, match="AUTH_SESSION_CACHE_TTL_SECONDS"):
        settings.validate_deployment()
    with pytest.raises(ValueError, match="AUTH_SESSION_CACHE_TTL_SECONDS"):
        AuthSessionCache(ttl)


def test_five_hour_window_reuses_checks_after_one_minute_but_not_past_token_expiry(session_context):
    c = session_context
    cache = AuthSessionCache(18000, clock=lambda: c.clock.tick, wall_clock=lambda: c.clock.wall)
    c.client.app.state.auth_session_cache = cache
    assert c.client.get("/me", headers=c.headers).status_code == 200
    c.clock.tick += 300
    c.clock.wall += 300
    assert c.client.get("/me", headers=c.headers).status_code == 200
    assert revocation_checks(c) == [True, False]
    c.security.read.assert_called_once()
    c.clock.tick += 3300
    c.clock.wall += 3300
    c.verify.side_effect = auth.ExpiredIdTokenError("expired", cause=None)
    assert c.client.get("/me", headers=c.headers).status_code == 401
    assert revocation_checks(c) == [True, False, True]
    assert cache.get(cache.token_key("test-token")) is None


def test_five_hour_limit_remains_fixed_even_for_a_longer_lived_token():
    clock = SimpleNamespace(tick=10, wall=100)
    cache = AuthSessionCache(18000, clock=lambda: clock.tick, wall_clock=lambda: clock.wall)
    key = cache.token_key("token")
    cache.remember(key, {"uid": "caregiver", "exp": 40000}, {}, started=10, revision=0)
    clock.tick += 17999
    clock.wall += 17999
    assert cache.get(key) is not None
    clock.tick += 1
    clock.wall += 1
    assert cache.get(key) is None


@pytest.mark.parametrize("ttl", [0, 60, 300, 301, 18000])
def test_supported_cache_windows_are_accepted(ttl):
    value = Settings()
    value.APP_ENV = "development"
    value.AUTH_SESSION_CACHE_TTL_SECONDS = ttl
    value.validate_deployment()
    assert AuthSessionCache(ttl).ttl_seconds == ttl


def test_mfa_mutation_invalidates_checks_created_while_it_was_running(session_context):
    c = session_context
    assert c.client.get("/me", headers=c.headers).status_code == 200

    def mutate(uid):
        key = c.cache.token_key("test-token")
        revision = c.cache.invalidate_user(uid)
        c.cache.remember(key, c.claims, c.security.read.return_value, started=c.clock.tick, revision=revision)
        assert c.cache.get(key) is not None

    c.security.disable_mfa.side_effect = mutate
    response = c.client.post("/me/security/mfa/disable", headers=c.headers)
    assert response.status_code == 204
    assert c.cache.get(c.cache.token_key("test-token")) is None
    assert c.client.get("/me", headers=c.headers).status_code == 200
    assert revocation_checks(c) == [True, True, True]


@pytest.mark.parametrize("path", ["/me/data", "/api/v1/me"])
def test_account_deletions_refresh_auth_and_clear_session_cache(session_context, monkeypatch, path):
    from backend.api.dependencies import get_caregiver_data_service

    c = session_context
    data = Mock()
    monkeypatch.setitem(c.client.app.dependency_overrides, get_caregiver_data_service, lambda: data)
    assert c.client.get("/me", headers=c.headers).status_code == 200
    with patch("backend.api.v1.endpoints.auth.auth.delete_user"):
        assert c.client.delete(path, headers=c.headers).status_code == 204
    data.delete_account_data.assert_called_once_with("caregiver")
    assert c.cache.get(c.cache.token_key("test-token")) is None
    assert revocation_checks(c) == [True, True]


def test_coach_reuses_session_but_still_checks_current_consent(session_context, monkeypatch):
    from backend.api.consent import require_processing_consent
    from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
    from backend.core.privacy import CONSENT_VERSION
    from backend.services.coaching import CoachingResult

    c = session_context
    data = Mock()
    data.get_child.return_value = {"age_months": 6, "completed_months": 6, "age_days": 183, "in_scope": True}
    data.get_consent.return_value = {"consent_version": CONSENT_VERSION, "consent_at": "recorded",
                                     "caregiver_authority": True}
    data.create_interaction.return_value = "answer-1"
    retrieval, coaching = Mock(), Mock()
    retrieval.retrieve.return_value = []
    coaching.generate.return_value = CoachingResult("Talk gently with your baby.", [], answer_basis="general_information")
    monkeypatch.delitem(c.client.app.dependency_overrides, require_processing_consent)
    monkeypatch.setitem(c.client.app.dependency_overrides, get_caregiver_data_service, lambda: data)
    monkeypatch.setitem(c.client.app.dependency_overrides, get_coaching_service, lambda: coaching)
    monkeypatch.setitem(c.client.app.dependency_overrides, get_retrieval_service, lambda: retrieval)
    assert c.client.get("/me", headers=c.headers).status_code == 200
    for path in ("/coach", "/api/v1/coach"):
        response = c.client.post(path, headers=c.headers, json={"child_id": "child-1", "question": "Play ideas"})
        assert response.status_code == 200
    assert coaching.generate.call_count == 2
    data.get_consent.return_value = {}
    response = c.client.post("/coach", headers=c.headers, json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code == 403
    assert response.headers["X-Consent-Required"] == "true"
    assert coaching.generate.call_count == 2
    assert data.get_consent.call_count == 3
    assert revocation_checks(c) == [True, False, False, False]
    c.security.read.assert_called_once_with("caregiver")
