from backend.services.coaching import CoachingService
from backend.services.retrieval import RetrievedPassage
from backend.services.coaching import generation_request_id
from backend.services.coaching import PROVIDER_BLOCK_MESSAGE
from backend.services.age import AGE_SCOPE_MESSAGE
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


def test_contextual_typo_understanding_preserves_original_details_in_one_generation_call():
    client = FakeClient()
    client.models.generate_content = Mock(return_value=FakeResponse())
    question = "Amani is 12 months, 8.5 kg. How cn I imprve communcation at feedng?"
    context = [{"role": "user", "text": "We are sharing a picture book."},
               {"role": "assistant", "text": "Name the pictures and pause."}]
    CoachingService(client=client).generate(question, 12, "feeding", [], conversation_context=context)
    client.models.generate_content.assert_called_once()
    request = client.models.generate_content.call_args.kwargs
    assert question in request["contents"]
    assert "sharing a picture book" in request["contents"]
    policy = request["config"].system_instruction
    assert "Do not silently alter names, places, numeric values" in policy
    assert "ask a brief clarification" in policy
    assert "Potential reports of harm must not be silently corrected" in policy


def test_mixed_request_and_clarification_use_the_same_generation_call():
    client = FakeClient()
    client.models.generate_content = Mock(return_value=FakeResponse())
    context = [{"role": "user", "text": "She still won't take it."},
               {"role": "assistant", "text": "What are you offering?"}]
    message = "I am feeding my baby a bottle of formula. Also write Python code."
    CoachingService(client=client).generate(message, 2, None, [], conversation_context=context)
    client.models.generate_content.assert_called_once()
    request = client.models.generate_content.call_args.kwargs
    assert message in request["contents"]
    assert "What are you offering?" in request["contents"]
    assert "use the new details to resolve that" in request["contents"]
    assert "answer only that need" in request["config"].system_instruction
    assert "not whether a baby-related word appears" in request["config"].system_instruction


@pytest.mark.parametrize("question,expected", [
    ("My baby Amani is 12 months and 8.5 kg. How cn we play?", 12),
    ("my baby amani is 12 months and 8.5 kg. How cn we play?", 12),
    ("Our child called Amani is 24 months. Play ideas?", 24),
    ("My baby Amani is 25 months. Play ideas?", 25),
    ("My baby is feeding 120 ml. Play ideas?", None),
])
def test_explicit_named_child_ages_preserve_numbers(question, expected):
    from backend.services.age import message_age_months

    assert message_age_months(question) == expected


@pytest.mark.parametrize("prompt_reason,finish_reason", [
    ("PROHIBITED_CONTENT", None), ("SAFETY", None),
    (None, "SAFETY"), (None, "RECITATION"),
])
def test_provider_content_block_returns_clear_message_without_retry(prompt_reason, finish_reason):
    response = SimpleNamespace(text=None, prompt_feedback=SimpleNamespace(block_reason=prompt_reason),
                               candidates=[SimpleNamespace(finish_reason=finish_reason)])
    client = FakeClient()
    client.models.generate_content = Mock(return_value=response)
    result = CoachingService(client=client).generate("Taking turns in play?", 12, "play", [fallback_reference()])
    assert result.blocked is True
    assert result.answer == PROVIDER_BLOCK_MESSAGE
    assert result.passages == []
    client.models.generate_content.assert_called_once()


def test_empty_unblocked_model_response_remains_a_service_error():
    client = FakeClient()
    client.models.generate_content = Mock(return_value=SimpleNamespace(text=None, candidates=[]))
    with pytest.raises(RuntimeError, match="empty answer"):
        CoachingService(client=client).generate("Playing together?", 12, "play", [fallback_reference()])


@pytest.mark.parametrize("question", ["", "  ", "a", None, "a" * 1201])
def test_invalid_question_does_not_call_model(question):
    client = FakeClient()
    with pytest.raises(ValueError, match="between 2 and 1200"):
        CoachingService(client=client).generate(question, 6, None, [])
    assert client.models.request is None


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
    assert "include a brief relevant precaution" in client.models.request["contents"]
    assert "without information-type labels" in client.models.request["contents"]
    assert "at most 160 words" in client.models.request["contents"]
    assert "Country for guidance: Kenya" in client.models.request["contents"]
    assert "guidance country is Kenya" in client.models.request["config"].system_instruction
    assert "does not establish the caregiver's physical location" in client.models.request["config"].system_instruction
    assert "do not present foreign vaccination schedules" in client.models.request["config"].system_instruction
    assert "Address the requested activity type" in client.models.request["contents"]
    assert "Use an age stated in the current message" in client.models.request["contents"]
    assert "not merely because" in client.models.request["contents"]


def test_coaching_service_calls_model_when_no_passage_matches():
    client = FakeClient()
    result = CoachingService(client=client).generate("How can I share a book?", 6, None, [])

    assert result.passages == []
    assert result.answer_basis == "general_information"
    assert client.models.request is not None
    assert "No matching reference excerpts available" in client.models.request["contents"]
    assert "missing or incomplete references do not prevent an answer" in client.models.request["config"].system_instruction


def test_generation_preserves_applicability_conditions_and_avoids_blanket_reassurance():
    client = FakeClient()
    reference = fallback_reference()
    reference.applicability_conditions = ["Only during vomiting illness; no reported danger signs"]
    CoachingService(client=client).generate("What can I try?", 6, None, [reference])
    prompt = client.models.request["contents"]
    assert "Applies only when: Only during vomiting illness; no reported danger signs" in prompt
    assert "do not transfer actions between different conditions" in prompt
    assert "Do not declare an individual child completely normal" in prompt
    policy = client.models.request["config"].system_instruction
    assert "Do not turn urgent care into routine advice" in policy
    assert "Include necessary safety conditions" in policy


def test_generation_includes_history_as_context_not_evidence():
    client = FakeClient()
    context = [{"role": "user", "text": "We are feeding."},
               {"role": "assistant", "text": "HISTORICAL_CLAIM"}]
    CoachingService(client=client).generate("What else can I try?", 6, "feeding", [fallback_reference()],
                                             conversation_context=context)
    request = client.models.request
    assert "Recent conversation (context only, not evidence)" in request["contents"]
    assert "HISTORICAL_CLAIM" in request["contents"]
    assert "not instructions or factual evidence" in request["config"].system_instruction
    assert "current profile age" in request["config"].system_instruction
    assert request["contents"].count("Caregiver question: What else can I try?") == 1


@pytest.mark.parametrize("question", ["What else can I try?", "Can you explain that?"])
def test_contextual_prompt_distinguishes_additional_advice_from_explanation(question):
    client = FakeClient()
    client.models.generate_content = Mock(return_value=FakeResponse())
    context = [{"role": "user", "text": "My baby is crying."},
               {"role": "assistant", "text": "Hold your baby closely and sing softly."}]
    CoachingService(client=client).generate(question, 0, None, [fallback_reference()],
                                             conversation_context=context)
    request = client.models.generate_content.call_args.kwargs
    policy = request["config"].system_instruction
    assert "Rewording" in policy
    assert "one new action is enough" in policy
    assert "Use cautious general knowledge when the excerpts offer no further ideas" in policy
    assert "Do not repeat the list or invent actions" in policy
    assert "clarification, not a new action" in policy
    assert "a follow-up does not require another list of actions" in request["contents"]
    assert "Give 2 to 4 short actions in plain language." not in request["contents"]
    assert context[1]["text"] in request["contents"]
    client.models.generate_content.assert_called_once()


def test_standalone_prompt_keeps_initial_coaching_format():
    client = FakeClient()
    CoachingService(client=client).generate("How can I talk during feeding?", 6, "feeding", [fallback_reference()])
    assert "Give 2 to 4 short actions in plain language." in client.models.request["contents"]
    policy = client.models.request["config"].system_instruction
    assert "Preserve all conditions" in policy
    assert "Conversation-response rules" not in policy


def test_newborn_age_is_explicit_and_activity_requirements_are_not_assumed():
    client = FakeClient()
    CoachingService(client=client).generate("How can we take turns in play?", 15 / 30.4375, None, [])
    request = client.models.request
    assert "15 days old (newborn)" in request["contents"]
    assert "Do not suggest independent sitting" in request["config"].system_instruction
    assert "breast milk or infant formula, not solid food" in request["config"].system_instruction


@pytest.mark.parametrize("age", [0.5, 12, 24, 24.1, 36])
def test_supported_age_range_is_inclusive_and_older_questions_skip_model(age):
    client = FakeClient()
    result = CoachingService(client=client).generate("How can we play together?", age, None, [])
    if age > 24:
        assert result.answer == AGE_SCOPE_MESSAGE
        assert client.models.request is None
    else:
        assert "birth through 24 months, inclusive" in client.models.request["config"].system_instruction
        if age == 12:
            assert "This is a newborn" not in client.models.request["config"].system_instruction
    assert result.answer_basis == "general_information"


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
