from backend.services.coaching import CoachingService
from backend.services.retrieval import RetrievedPassage
from backend.services.coaching import generation_request_id
from types import SimpleNamespace
import logging

import pytest
from google.genai import errors
from unittest.mock import Mock


class FakeResponse:
    text = "Try talking about what you are doing during feeding. Pause and respond to your baby's sounds."


class FakeModels:
    def __init__(self):
        self.request = None

    def generate_content(self, **kwargs):
        self.request = kwargs
        return FakeResponse()


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


def test_coaching_service_includes_only_retrieved_passages_in_prompt():
    client = FakeClient()
    passage = RetrievedPassage(
        passage_id="passage-1", text="Talk with your baby during feeding.", title="Talk during feeding",
        source_title="Reach Up", pdf_page=41, source_url="https://example.test/source", score=0.8,
        source_age_label="6-8 months", routines=["feeding"],
    )

    result = CoachingService(client=client).generate("How can I talk at feeding time?", 6, "feeding", [passage])

    assert result.answer.startswith("Try talking")
    assert result.passages == [passage]
    assert "Talk with your baby during feeding" in client.models.request["contents"]
    assert "Do not diagnose" in client.models.request["contents"]


def test_coaching_service_returns_a_safe_message_when_no_passage_matches():
    result = CoachingService(client=FakeClient()).generate("How do I treat a fever?", 6, None, [])

    assert result.passages == []
    assert "health worker" in result.answer


def quota_error():
    return errors.ClientError(429, {"error": {"message": "Quota exceeded"}})


def fallback_reference():
    return RetrievedPassage("p1", "Talk during feeding.", "Title", "Source", 1,
                            "https://example.test", 0.8, "6-8 months", [])


def test_quota_fallback_preserves_prompt_and_references(caplog):
    client = FakeClient()
    client.models.generate_content = Mock(side_effect=[quota_error(), FakeResponse()])
    reference = fallback_reference()
    with caplog.at_level(logging.INFO, logger="uvicorn.error.coaching_timing"):
        result = CoachingService(client=client, model="primary", fallback_model="fallback").generate(
            "PRIVATE_QUESTION", 6, "feeding", [reference],
        )
    first, second = client.models.generate_content.call_args_list
    assert first.kwargs["model"] == "primary"
    assert second.kwargs["model"] == "fallback"
    assert first.kwargs["contents"] == second.kwargs["contents"]
    assert first.kwargs["config"] == second.kwargs["config"]
    assert result.passages == [reference]
    assert "model=fallback" in caplog.text
    assert "PRIVATE_QUESTION" not in caplog.text


@pytest.mark.parametrize("fallback", ["", "primary"])
def test_disabled_or_duplicate_fallback_does_not_retry(fallback):
    client = FakeClient()
    client.models.generate_content = Mock(side_effect=quota_error())
    with pytest.raises(errors.ClientError):
        CoachingService(client=client, model="primary", fallback_model=fallback).generate(
            "Question", 6, None, [fallback_reference()],
        )
    client.models.generate_content.assert_called_once()


@pytest.mark.parametrize("error", [
    errors.ClientError(403, {"error": {"message": "Forbidden"}}),
    errors.ServerError(503, {"error": {"message": "Unavailable"}}),
    TimeoutError("Timed out"),
    RuntimeError("Unexpected failure"),
])
def test_non_quota_errors_do_not_trigger_fallback(error):
    client = FakeClient()
    client.models.generate_content = Mock(side_effect=error)
    with pytest.raises(type(error)):
        CoachingService(client=client, model="primary", fallback_model="fallback").generate(
            "Question", 6, None, [fallback_reference()],
        )
    client.models.generate_content.assert_called_once()


def test_both_models_exhausted_stop_after_two_attempts():
    client = FakeClient()
    client.models.generate_content = Mock(side_effect=[quota_error(), quota_error()])
    with pytest.raises(errors.ClientError):
        CoachingService(client=client, model="primary", fallback_model="fallback").generate(
            "Question", 6, None, [fallback_reference()],
        )
    assert client.models.generate_content.call_count == 2


def test_successful_primary_does_not_call_fallback():
    client = FakeClient()
    client.models.generate_content = Mock(return_value=FakeResponse())
    CoachingService(client=client, model="primary", fallback_model="fallback").generate(
        "Question", 6, None, [fallback_reference()],
    )
    client.models.generate_content.assert_called_once()


def test_sdk_client_has_one_attempt_without_changing_timeout(monkeypatch):
    factory = Mock()
    monkeypatch.setattr("backend.services.coaching.genai.Client", factory)
    CoachingService(api_key="test-key").client
    options = factory.call_args.kwargs["http_options"]
    assert options.retry_options.attempts == 1
    assert options.timeout is None


def test_generation_diagnostics_log_phases_and_counts_without_content(caplog):
    client = FakeClient()
    response = SimpleNamespace(text="PRIVATE_ANSWER", usage_metadata=SimpleNamespace(
        prompt_token_count=100, candidates_token_count=20,
        thoughts_token_count=200, total_token_count=320,
    ))
    client.models.generate_content = lambda **kwargs: response
    reference = RetrievedPassage("p1", "PRIVATE_REFERENCE", "Title", "Source", 1,
                                 "https://example.test", 0.8, "6-8 months", [])
    token = generation_request_id.set("diagnostic-trace")
    try:
        with caplog.at_level(logging.INFO, logger="uvicorn.error.coaching_timing"):
            result = CoachingService(api_key="PRIVATE_KEY", client=client).generate(
                "PRIVATE_QUESTION", 6, None, [reference],
            )
    finally:
        generation_request_id.reset(token)
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert result.answer == "PRIVATE_ANSWER"
    for phase in ("client_initialization", "sdk_request", "response_handling"):
        assert f"request=diagnostic-trace phase={phase} event=started" in messages
        assert f"request=diagnostic-trace phase={phase} event=completed seconds=" in messages
    assert "prompt_tokens=100 answer_tokens=20 thought_tokens=200 total_tokens=320" in messages
    for private in ("PRIVATE_KEY", "PRIVATE_QUESTION", "PRIVATE_REFERENCE", "PRIVATE_ANSWER"):
        assert private not in messages


def test_generation_error_diagnostics_do_not_expose_exception_text(caplog):
    client = FakeClient()

    def fail(**kwargs):
        raise RuntimeError("PRIVATE_ERROR_DETAILS")

    client.models.generate_content = fail
    reference = RetrievedPassage("p1", "Reference", "Title", "Source", 1,
                                 "https://example.test", 0.8, "6-8 months", [])
    with caplog.at_level(logging.INFO, logger="uvicorn.error.coaching_timing"):
        with pytest.raises(RuntimeError, match="PRIVATE_ERROR_DETAILS"):
            CoachingService(client=client).generate("Question", 6, None, [reference])
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "phase=sdk_request event=failed" in messages
    assert "error_type=RuntimeError" in messages
    assert "PRIVATE_ERROR_DETAILS" not in messages
