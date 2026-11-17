"""Language boundaries use the real offline detector and the shared API path."""

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.core.security import require_authenticated_user
from backend.schemas.conversations import ConversationMessageResponse
from backend.services.coaching import CoachingResult
from backend.services.conversation_context import select_conversation_context
from backend.services.language_safety import LANGUAGE_MESSAGE, supports_english
from scripts.evaluate_language_safety import evaluate, load_cases, meets_gate


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["id"])
def test_language_development_cases(case):
    assert supports_english(case["question"]) is case["should_allow"]


def test_language_gate_fails_closed_when_detector_is_unavailable(monkeypatch):
    monkeypatch.setattr("backend.services.language_safety.language_detector", Mock(side_effect=RuntimeError("unavailable")))
    assert not supports_english("How can I encourage babbling?")


def test_experimental_language_spans_do_not_reject_fluent_english():
    assert supports_english("Now a different question: my eight-week-old wakes when I transfer him into the cot. Give two settling ideas.")
    assert not supports_english("My baby ne respire pas")
    assert not supports_english("I have a question about my baby: necesito ayuda ahora")


def test_language_gate_does_not_allow_non_english_appended_to_short_exceptions():
    assert not supports_english("Hello, mtoto wangu ana homa")
    assert not supports_english("18 months mtoto wangu")
    assert not supports_english("My baby ana ho\u200bma")


def test_language_report_detects_both_misses_and_false_rejections():
    report = evaluate(load_cases(), inspector=lambda _: True)
    assert report["unsupported_allowed"] > 0 and not meets_gate(report)
    report = evaluate(load_cases(), inspector=lambda _: False)
    assert report["english_refused"] > 0 and not meets_gate(report)
    assert meets_gate(evaluate(load_cases()))


@pytest.fixture
def language_api(client, monkeypatch):
    data, retrieval, coaching = Mock(), Mock(), Mock()
    data.get_child.return_value = {"age_months": 2, "completed_months": 2, "age_days": 60, "in_scope": True}
    data.get_conversation.return_value = {"messages": []}
    data.create_interaction.return_value = "interaction-1"
    data.save_conversation_turn.return_value = "answer-1"
    retrieval.retrieve.return_value = []
    coaching.generate.return_value = CoachingResult("Talk gently with your baby.", [], answer_basis="general_information")
    def provider(value):
        return lambda: value
    for dependency, value in ((require_authenticated_user, {"uid": "account-a"}),
                              (get_caregiver_data_service, data), (get_coaching_service, coaching),
                              (get_retrieval_service, retrieval)):
        monkeypatch.setitem(client.app.dependency_overrides, dependency, provider(value))
    return SimpleNamespace(client=client, data=data, retrieval=retrieval, coaching=coaching)


def post(api, question, stream=False, **values):
    response = api.client.post("/coach", json={"child_id": "child-1", "question": question, **values},
                               headers={"Accept": "text/event-stream"} if stream else {})
    assert response.status_code == 200, response.text
    if not stream:
        return response.json()
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert not any("text" in event for event in events)  # No generated preview.
    return events[-1]["response"]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("question", ["Mtoto wangu ana homa", "My baby ana homa", "Mon bébé ne veut pas dormir"])
def test_unsupported_input_never_reaches_retrieval_or_generation(language_api, question, stream):
    result = post(language_api, question, stream)
    assert result["answer"] == LANGUAGE_MESSAGE
    assert result["status"] == "no_evidence" and result["response_kind"] == "unsupported_language"
    assert result["citations"] == [] and not result["health_context_used"]
    language_api.retrieval.retrieve.assert_not_called()
    language_api.coaching.generate.assert_not_called()
    assert language_api.data.create_interaction.call_args.kwargs["response_kind"] == "unsupported_language"


@pytest.mark.parametrize("stream", [False, True])
def test_recognized_danger_takes_priority_over_language_boundary(language_api, stream):
    result = post(language_api, "My baby cannot breathe, mtoto wangu", stream)
    assert result["status"] == "escalated" and result["safety"] == "escalate"
    language_api.coaching.generate.assert_not_called()
    language_api.retrieval.retrieve.assert_not_called()


def test_english_input_still_reaches_generation(language_api):
    assert post(language_api, "How can I encourage babbling?")["status"] == "answered"
    language_api.coaching.generate.assert_called_once()


def test_language_boundary_survives_storage_failure(language_api):
    language_api.data.create_interaction.side_effect = RuntimeError("offline")
    result = post(language_api, "Mtoto wangu ana homa")
    assert result["answer"] == LANGUAGE_MESSAGE and result["interaction_id"] is None


def test_language_boundary_is_saved_and_excluded_from_later_context(language_api):
    result = post(language_api, "Mtoto wangu ana homa", conversation_id="chat-1")
    stored = language_api.data.save_conversation_turn.call_args.args[-1]
    assert stored["response_kind"] == "unsupported_language"
    assistant = ConversationMessageResponse(id="answer-1", role="assistant", created_at=datetime.now(timezone.utc), **stored)
    assert assistant.response_kind == "unsupported_language" and result["message_id"] == "answer-1"
    messages = [{"role": "user", "text": "Mtoto wangu ana homa"}, assistant.model_dump()]
    assert select_conversation_context(messages) == []
