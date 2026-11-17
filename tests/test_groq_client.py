"""Exercise provider transport, privacy boundaries and the shared coaching flow offline."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from backend.core.config import Settings, settings
from backend.core.privacy import generation_notice
from backend.services.coaching import CoachingService, PROVIDER_BLOCK_MESSAGE
from backend.services.groq_client import GenerationProviderError, GroqClient


MODEL = "qwen/qwen3.8-27b"
CONFIG = SimpleNamespace(system_instruction="System policy", temperature=0.2)


def reply(content="Talk softly and pause for your baby's sounds.", finish="stop", **message):
    return {"choices": [{"finish_reason": finish, "message": {"content": content, **message}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 12, "total_tokens": 132}}


def test_real_coaching_flow_sends_context_to_fixed_host_and_returns_only_answer(caplog):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=reply(reasoning="PRIVATE_REASONING"))

    transport = GroqClient("PRIVATE_KEY", transport=httpx.MockTransport(respond))
    try:
        with caplog.at_level("INFO", logger="uvicorn.error.coaching_timing"):
            result = CoachingService(provider="groq", client=transport, model=MODEL).generate(
                "sorry I meant she is 23 months", 23, None, [], conversation_context=[
                    {"role": "user", "text": "At what time should I feed a 3 year old some chillies?"},
                    {"role": "assistant", "text": "Birth through 24 months only.",
                     "response_kind": "age_out_of_scope", "status": "no_evidence"},
                ],
            )
        assert result.answer == reply()["choices"][0]["message"]["content"]
        assert len(requests) == 1
        request = requests[0]
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer PRIVATE_KEY"
        payload = json.loads(request.content)
        assert payload["reasoning_effort"] == "none"
        assert payload["include_reasoning"] is False
        assert payload["max_completion_tokens"] == 350
        assert "chillies" in payload["messages"][1]["content"]
        assert "23 months" in payload["messages"][1]["content"]
        assert "Do not interpret test values" in payload["messages"][0]["content"]
        assert "provider=groq" in caplog.text
        assert all(text not in caplog.text for text in ("PRIVATE_KEY", "PRIVATE_REASONING", result.answer))
    finally:
        transport.close()


@pytest.mark.parametrize("model,cap,expected", [
    (MODEL, 220, 220), (MODEL, 650, 650),
    ("openai/gpt-oss-20b", 220, 1024),
    ("openai/gpt-oss-120b", 650, 1024),
    ("openai/gpt-oss-120b", 1500, 1500),
])
def test_provider_payload_keeps_reasoning_allowance_separate_from_answer_length(model, cap, expected):
    config = SimpleNamespace(system_instruction="System policy", temperature=0.2, max_output_tokens=cap)
    payload = GroqClient._payload(model, "A synthetic request", config)
    assert payload["max_completion_tokens"] == expected
    assert payload["reasoning_effort"] == ("none" if model == MODEL else "low")


@pytest.mark.parametrize("body", [
    reply("", finish="stop"), reply("Partial answer", finish="length"),
    reply(None, finish="tool_calls"), {}, {"choices": []}, {"choices": None},
    {"choices": [{"message": {"content": "No finish status"}}]},
])
def test_incomplete_or_malformed_answers_are_never_delivered(body):
    client = GroqClient("key", transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    try:
        with pytest.raises(GenerationProviderError):
            client.generate(model=MODEL, contents="Question", config=CONFIG)
    finally:
        client.close()


@pytest.mark.parametrize("status", [302, 401, 429, 500, 503])
def test_errors_do_not_retry_follow_redirects_or_expose_provider_body(status):
    handler = Mock(return_value=httpx.Response(status, json={"error": "PRIVATE_QUESTION_AND_KEY"},
                                              headers={"Location": "https://example.test/steal"}))
    client = GroqClient("PRIVATE_KEY", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(GenerationProviderError) as error:
            client.generate(model=MODEL, contents="PRIVATE_QUESTION", config=CONFIG)
        assert error.value.code == status
        assert "PRIVATE" not in str(error.value)
        handler.assert_called_once()
    finally:
        client.close()


def test_timeout_is_sanitized_without_retry():
    handler = Mock(side_effect=httpx.ReadTimeout("PRIVATE_RESPONSE"))
    client = GroqClient("key", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(GenerationProviderError, match="Generation service is unavailable") as error:
            client.generate(model=MODEL, contents="Question", config=CONFIG)
        assert error.value.kind == "transport"
        handler.assert_called_once()
    finally:
        client.close()


@pytest.mark.parametrize("body", [reply(None, finish="content_filter"), reply(None, refusal="Blocked")])
def test_provider_block_uses_existing_application_response(body):
    client = GroqClient("key", transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    try:
        result = CoachingService(provider="groq", client=client, model=MODEL).generate("Play ideas?", 12, None, [])
        assert result.blocked is True
        assert result.answer == PROVIDER_BLOCK_MESSAGE
    finally:
        client.close()


def test_pooled_client_is_created_once_and_closed_with_service(monkeypatch):
    client = Mock()
    factory = Mock(return_value=client)
    monkeypatch.setattr("backend.services.coaching.GroqClient", factory)
    service = CoachingService(provider="groq", api_key="key", model=MODEL)
    assert service.client is service.client
    factory.assert_called_once_with("key")
    service.close()
    service.close()
    client.close.assert_called_once()
    with pytest.raises(RuntimeError, match="closed"):
        _ = service.client


def test_groq_uses_its_own_model_and_permission_flags(monkeypatch):
    value = Settings()
    value.COACHING_PROVIDER = "groq"
    value.GEMINI_API_KEY = "gemini-key"
    value.GROQ_API_KEY = "groq-key"
    value.GROQ_MODEL = MODEL
    value.GROQ_FALLBACK_MODEL = ""
    value.GEMINI_PAID_SERVICES_CONFIRMED = True
    value.GEMINI_NONPERSONAL_TESTING_CONFIRMED = True
    value.GROQ_DATA_TERMS_CONFIRMED = False
    value.GROQ_NONPERSONAL_TESTING_CONFIRMED = False
    value.validate_coaching()
    assert value.coaching_model == MODEL
    assert value.coaching_fallback_model == ""
    assert value.provider_data_allowed is False
    value.APP_ENV = "production"
    value.ALLOWED_HOSTS = ["example.test"]
    with pytest.raises(ValueError, match="selected provider"):
        value.validate_deployment()
    value.GROQ_DATA_TERMS_CONFIRMED = True
    value.validate_deployment()
    monkeypatch.setattr(settings, "GROQ_DATA_TERMS_CONFIRMED", False)
    monkeypatch.setattr(settings, "GROQ_NONPERSONAL_TESTING_CONFIRMED", False)
    monkeypatch.setattr(settings, "GEMINI_PAID_SERVICES_CONFIRMED", True)
    client = Mock()
    client.generate.return_value = SimpleNamespace(text="Answer", blocked=False)
    CoachingService(provider="groq", client=client, model=MODEL).generate(
        "Meal ideas?", 18, None, [], profile_context={"health_details": {"allergies": "PRIVATE_ALLERGY"}},
    )
    assert "PRIVATE_ALLERGY" not in client.generate.call_args.kwargs["contents"]
    monkeypatch.setattr(settings, "GROQ_NONPERSONAL_TESTING_CONFIRMED", True)
    CoachingService(provider="groq", client=client, model=MODEL).generate(
        "Meal ideas?", 18, None, [], profile_context={"health_details": {"allergies": "EXAMPLE_ALLERGY"}},
    )
    assert "EXAMPLE_ALLERGY" in client.generate.call_args.kwargs["contents"]


def test_groq_quota_has_no_cross_provider_fallback(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_FALLBACK_MODEL", "")
    monkeypatch.setattr(settings, "GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
    client = Mock()
    client.generate.side_effect = GenerationProviderError(429)
    with pytest.raises(GenerationProviderError):
        CoachingService(provider="groq", client=client, model=MODEL).generate("Meal ideas?", 18, None, [])
    client.generate.assert_called_once()


@pytest.mark.parametrize("changes", [
    {"COACHING_PROVIDER": "unknown"}, {"GROQ_API_KEY": ""},
    {"GROQ_MODEL": "invalid"}, {"GROQ_FALLBACK_MODEL": "gemini-3.8-flash"},
])
def test_invalid_groq_settings_fail_before_requests(changes):
    value = Settings()
    value.COACHING_PROVIDER = "groq"
    value.GROQ_API_KEY = "key"
    value.GROQ_MODEL = MODEL
    value.GROQ_FALLBACK_MODEL = ""
    for field, setting in changes.items():
        setattr(value, field, setting)
    with pytest.raises(ValueError):
        value.validate_coaching()


def test_provider_switch_requires_different_notice_and_preserves_feedback_permission():
    from backend.core.privacy import FEEDBACK_CONSENT_VERSIONS

    gemini_version, gemini_label = generation_notice("gemini")
    groq_version, groq_label = generation_notice("groq")
    assert gemini_version != groq_version
    assert "Groq" in groq_label and "Gemini" in gemini_label
    assert {gemini_version, groq_version} <= FEEDBACK_CONSENT_VERSIONS
