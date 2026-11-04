"""Quota failover preserves context, resets previews and bounds provider attempts."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

from google.genai import errors
import pytest

from backend.core.config import Settings
from backend.core.privacy import generation_notice, FEEDBACK_CONSENT_VERSIONS
from backend.services.coaching import CoachingResult
from backend.services.groq_client import GenerationProviderError
from backend.services.provider_failover import ProviderFailoverService, retry_delay


@pytest.fixture
def routing():
    clock = SimpleNamespace(now=100)
    result = CoachingResult("Talk gently and pause.", [], answer_basis="general_information")
    services = {name: Mock(model=name+"-model") for name in ("groq", "gemini")}
    for service in services.values():
        service.generate.return_value = result
    router = ProviderFailoverService(services=services, primary="groq", clock=lambda: clock.now)
    return SimpleNamespace(router=router, services=services, clock=clock, result=result)


@pytest.mark.parametrize("primary", ["groq", "gemini"])
def test_either_provider_can_fall_back_without_leaking_quota_errors(routing, primary):
    c = routing
    other = "gemini" if primary == "groq" else "groq"
    router = ProviderFailoverService(services=c.services, primary=primary, clock=lambda: c.clock.now)
    c.services[primary].generate.side_effect = GenerationProviderError(429)
    context = {"conversation_context": [{"role": "user", "text": "Example context"}],
               "profile_context": {"milestones": ["Looks toward voices"]}}
    assert router.generate("How can I encourage babbling?", 6, "play", [], **context) is c.result
    assert c.services[primary].generate.call_args == c.services[other].generate.call_args
    assert c.services[primary].generate.call_count == c.services[other].generate.call_count == 1


def test_limited_provider_is_skipped_on_following_requests_and_retried_after_cooldown(routing):
    c = routing
    c.services["groq"].generate.side_effect = [GenerationProviderError(429), c.result]
    for _ in range(3):
        assert c.router.generate("Babbling ideas?", 6, None, []) is c.result
    assert c.services["groq"].generate.call_count == 1
    assert c.services["gemini"].generate.call_count == 3
    c.clock.now += 60
    assert c.router.generate("Babbling ideas?", 6, None, []) is c.result
    assert c.services["groq"].generate.call_count == 2
    assert c.services["gemini"].generate.call_count == 3


def test_success_does_not_duplicate_requests_or_send_to_both_services(routing):
    c = routing
    assert c.router.generate("Babbling ideas?", 6, None, []) is c.result
    c.services["groq"].generate.assert_called_once()
    c.services["gemini"].generate.assert_not_called()


def test_backup_quota_can_return_to_a_primary_whose_cooldown_just_finished(routing):
    c = routing
    c.router._limited_until["groq"] = 150

    def limited(*args, **kwargs):
        c.clock.now = 151
        raise GenerationProviderError(429)

    c.services["gemini"].generate.side_effect = limited
    assert c.router.generate("Babbling ideas?", 6, None, []) is c.result
    c.services["gemini"].generate.assert_called_once()
    c.services["groq"].generate.assert_called_once()


def test_both_limited_providers_fail_once_with_generic_availability_error(routing):
    c = routing
    for service in c.services.values():
        service.generate.side_effect = GenerationProviderError(429)
    for _ in range(2):
        with pytest.raises(GenerationProviderError) as failure:
            c.router.generate("Babbling ideas?", 6, None, [])
        assert failure.value.code == 503
        assert "quota" not in str(failure.value).lower()
    assert all(service.generate.call_count == 1 for service in c.services.values())


def test_partial_stream_is_cleared_before_backup_text_is_delivered(routing):
    c = routing
    events = []

    def primary(*args, on_delta, **kwargs):
        on_delta("Primary preview. ")
        raise GenerationProviderError(429)

    def backup(*args, on_delta, **kwargs):
        on_delta("Backup answer. ")
        return c.result

    c.services["groq"].generate.side_effect = primary
    c.services["gemini"].generate.side_effect = backup
    assert c.router.generate("Babbling ideas?", 6, None, [], on_delta=lambda text: events.append(text),
                             on_reset=lambda: events.append("RESET")) is c.result
    assert events == ["Primary preview. ", "RESET", "Backup answer. "]


def test_stream_without_reset_support_never_concatenates_two_answers(routing):
    c = routing

    def primary(*args, on_delta, **kwargs):
        on_delta("Partial. ")
        raise GenerationProviderError(429)

    c.services["groq"].generate.side_effect = primary
    with pytest.raises(GenerationProviderError) as failure:
        c.router.generate("Babbling ideas?", 6, None, [], on_delta=lambda _: None)
    assert failure.value.code == 503
    c.services["gemini"].generate.assert_not_called()


def test_cancel_during_switch_does_not_start_backup(routing):
    from backend.api.coaching_stream import StreamCancelled
    c = routing
    c.services["groq"].generate.side_effect = GenerationProviderError(429)
    with pytest.raises(StreamCancelled):
        c.router.generate("Babbling ideas?", 6, None, [], on_delta=lambda _: None,
                         on_reset=Mock(side_effect=StreamCancelled()))
    c.services["gemini"].generate.assert_not_called()


@pytest.mark.parametrize("code", [400, 401, 403, 503])
def test_non_quota_failures_are_not_hidden_by_provider_switching(routing, code):
    c = routing
    c.services["groq"].generate.side_effect = GenerationProviderError(code)
    with pytest.raises(GenerationProviderError) as failure:
        c.router.generate("Babbling ideas?", 6, None, [])
    assert failure.value.code == code
    c.services["gemini"].generate.assert_not_called()


def test_safety_refusal_is_not_retried_against_another_provider(routing):
    c = routing
    c.services["groq"].generate.return_value = CoachingResult("Blocked", [], blocked=True)
    assert c.router.generate("Example request?", 6, None, []).blocked
    c.services["gemini"].generate.assert_not_called()


@pytest.mark.parametrize("raw,expected", [("120", 120), ("0", 1), ("90000", 86400),
                                          ("invalid", 60), ("nan", 60), ("-1", 60)])
def test_groq_retry_metadata_has_safe_bounds(raw, expected):
    assert retry_delay(GenerationProviderError(429, retry_after_seconds=raw), 60) == expected


def test_gemini_structured_retry_info_is_honored(routing):
    c = routing
    c.services["groq"].generate.side_effect = errors.ClientError(429, {"error": {
        "message": "PRIVATE_PROVIDER_CONTENT", "details": [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "125.5s"}]}})
    c.router.generate("Babbling ideas?", 6, None, [])
    assert c.router._limited_until["groq"] == 225.5


def test_concurrent_backup_requests_do_not_corrupt_cooldown_state(routing):
    c = routing
    c.services["groq"].generate.side_effect = GenerationProviderError(429)
    c.router.generate("Babbling ideas?", 6, None, [])
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: c.router.generate("Babbling ideas?", 6, None, []), range(20)))
    assert all(result is c.result for result in results)
    assert c.services["groq"].generate.call_count == 1


def test_owned_services_disable_same_provider_retries_and_close_both(monkeypatch):
    services = []

    def build(**kwargs):
        assert kwargs["fallback_model"] == ""
        service = Mock(model="example")
        services.append(service)
        return service

    monkeypatch.setattr("backend.services.provider_failover.CoachingService", build)
    router = ProviderFailoverService(primary="groq")
    assert len(services) == 2
    router.close()
    router.close()
    for service in services:
        service.close.assert_called_once()


def test_borrowed_services_are_not_closed_and_closed_router_rejects_requests(routing):
    c = routing
    c.router.close()
    with pytest.raises(RuntimeError, match="closed"):
        c.router.generate("Babbling ideas?", 6, None, [])
    for service in c.services.values():
        service.close.assert_not_called()


def dual_settings():
    value = Settings()
    value.APP_ENV = "production"
    value.ALLOWED_HOSTS = ["example.test"]
    value.COACHING_PROVIDER = "groq"
    value.COACHING_PROVIDER_FAILOVER = True
    value.GROQ_API_KEY, value.GEMINI_API_KEY = "test-groq", "test-gemini"
    value.GROQ_MODEL, value.GEMINI_MODEL = "qwen/qwen3.8-27b", "gemini-test"
    value.GROQ_DATA_TERMS_CONFIRMED = value.GEMINI_PAID_SERVICES_CONFIRMED = True
    value.GROQ_NONPERSONAL_TESTING_CONFIRMED = value.GEMINI_NONPERSONAL_TESTING_CONFIRMED = False
    return value


def test_dual_provider_configuration_requires_both_keys_and_production_confirmations():
    value = dual_settings()
    value.validate_coaching()
    value.validate_deployment()
    value.GEMINI_API_KEY = ""
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        value.validate_coaching()
    value.GEMINI_PAID_SERVICES_CONFIRMED = False
    assert value.provider_data_allowed is False
    with pytest.raises(ValueError, match="every failover provider"):
        value.validate_deployment()


def test_dual_notice_names_both_services_and_differs_from_single_provider_consent():
    version, label = generation_notice("groq", True)
    assert version == generation_notice("gemini", True)[0]
    assert version not in {generation_notice("groq")[0], generation_notice("gemini")[0]}
    assert "Groq" in label and "Gemini" in label
    assert version in FEEDBACK_CONSENT_VERSIONS


def test_existing_single_provider_consent_cannot_send_to_the_backup(client, routing, monkeypatch):
    from datetime import datetime, timezone
    from backend.api.consent import require_processing_consent
    from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
    from backend.core.security import require_authenticated_user

    version = generation_notice("groq", True)[0]
    data = Mock()
    data.get_consent.return_value = {"consent_version": generation_notice("groq")[0],
                                      "consent_at": datetime.now(timezone.utc), "caregiver_authority": True}
    monkeypatch.setattr("backend.api.consent.CONSENT_VERSION", version)
    monkeypatch.delitem(client.app.dependency_overrides, require_processing_consent)
    monkeypatch.setitem(client.app.dependency_overrides, require_authenticated_user, lambda: {"uid": "account"})
    monkeypatch.setitem(client.app.dependency_overrides, get_caregiver_data_service, lambda: data)
    monkeypatch.setitem(client.app.dependency_overrides, get_coaching_service, lambda: routing.router)
    response = client.post("/coach", headers={"Accept": "text/event-stream"},
                           json={"child_id": "child", "question": "How can I encourage babbling?"})
    assert response.status_code == 403 and response.headers["X-Consent-Required"] == "true"
    for service in routing.services.values():
        service.generate.assert_not_called()
    data.get_consent.return_value["consent_version"] = version
    data.get_child.return_value = {"age_months": 6, "completed_months": 6, "age_days": 183, "in_scope": True}
    data.create_interaction.return_value = "answer-1"
    retrieval = Mock()
    retrieval.retrieve.return_value = []
    monkeypatch.setitem(client.app.dependency_overrides, get_retrieval_service, lambda: retrieval)
    routing.services["groq"].generate.side_effect = GenerationProviderError(429)
    response = client.post("/coach", json={"child_id": "child", "question": "How can I encourage babbling?"})
    assert response.status_code == 200
    assert response.json()["answer"] == routing.result.answer
