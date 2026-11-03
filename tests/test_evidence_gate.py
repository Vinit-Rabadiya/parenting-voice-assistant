from unittest.mock import MagicMock
from datetime import date
from google.genai import errors as genai_errors

import pytest

from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.core.security import require_authenticated_user
from backend.main import app
from backend.services.coaching import CoachingResult
from backend.services.coaching import PROVIDER_BLOCK_MESSAGE
from backend.services.evidence import select_evidence
from backend.services.retrieval import RetrievedPassage
from backend.services.response_safety import SAFE_RESPONSE
from backend.services.input_safety import ESCALATION_MESSAGE


@pytest.mark.parametrize("question", ["", "  ", "a", None, {}, "a" * 1201])
def test_invalid_question_is_rejected_before_processing(client, services, question):
    data, retrieval, coaching = services
    response = client.post("/coach", json={"child_id": "child-1", "question": question})
    assert response.status_code == 422
    data.get_child.assert_not_called()
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_coaching_requires_authentication(client, services):
    data, retrieval, coaching = services
    app.dependency_overrides.pop(require_authenticated_user)
    response = client.post("/coach", json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code == 401
    data.get_child.assert_not_called()
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_question_whitespace_is_trimmed():
    from backend.schemas.coaching import CoachingRequest

    assert CoachingRequest(child_id="child-1", question="  Play ideas  ").question == "Play ideas"


def test_age_scope_correction_and_answer_repair_keep_the_original_question(client, services):
    data, retrieval, coaching = services
    messages = []
    data.get_conversation.return_value = {"messages": messages}
    topic = "At what time should I feed a 3 year old some chillies?"

    def save(uid, conversation_id, child_id, question, routine, answer):
        messages.extend([{"role": "user", "text": question}, {"role": "assistant", **answer}])
        return f"message-{len(messages)}"

    data.save_conversation_turn.side_effect = save
    retrieval.retrieve.return_value = []
    coaching.generate.return_value = CoachingResult("Offer mild food rather than very spicy food.", [])
    for question, expected in [(topic, "no_evidence"), ("sorry I meant she is 23 months", "answered"),
                               ("you did not respond to the question", "answered")]:
        response = client.post("/coach", json={"child_id": "child-1", "conversation_id": "conversation-1", "question": question})
        assert response.status_code == 200
        assert response.json()["status"] == expected
        if expected == "answered":
            assert coaching.generate.call_args.args[1] == 23
            retrieval.retrieve.assert_not_called()
            assert coaching.generate.call_args.args[3][0].source_age_label == "6-25 months (upper bound excluded)"
            assert response.json()["caregiver_request"] == topic
    assert coaching.generate.call_count == 2


@pytest.mark.parametrize("topic,kind", [
    ("Write Python code for my 3 year old child.", "unrelated"),
    ("Calculate a medicine dose for my 3 year old child.", "professional_referral"),
])
def test_age_correction_cannot_bypass_the_retained_request_boundaries(client, services, topic, kind):
    data, retrieval, coaching = services
    data.get_conversation.return_value = {"messages": [
        {"role": "user", "text": topic},
        {"role": "assistant", "text": "Birth through 24 months only.", "status": "no_evidence", "response_kind": "age_out_of_scope"},
    ]}
    data.save_conversation_turn.return_value = "corrected"
    response = client.post("/coach", json={"child_id": "child-1", "conversation_id": "conversation-1",
                                            "question": "sorry I meant she is 23 months"})
    assert response.status_code == 200
    assert response.json()["response_kind"] == kind
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


@pytest.mark.parametrize("question,kind", [
    ("I am batting my baby.", "clarification"),
    ("I wnt to lern coding but dnt knw wer to start", "unrelated"),
    ("My baby is sleeping. Write Python code.", "unrelated"),
])
def test_input_interpretation_keeps_safety_and_topic_boundaries(client, services, question, kind):
    data, retrieval, coaching = services
    response = client.post("/coach", json={"child_id": "child-1", "question": question})
    assert response.status_code == 200
    assert response.json()["response_kind"] == kind
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    assert data.create_interaction.call_args.args[2] == question


def passage(score: float, text: str = "Talk with your baby during feeding.") -> RetrievedPassage:
    return RetrievedPassage("p1", text, "Feeding conversation", "Reference", 1,
                            "https://example.test/reference", score, "6-8 months", ["feeding"])


def test_gate_keeps_boundary_and_rejects_invalid_or_empty_evidence():
    accepted = passage(0.50)
    assert select_evidence([passage(0.49), passage(float("nan")), passage(float("inf")),
                            passage(0.9, " "), accepted], 0.50) == [accepted]


def test_provider_content_block_is_stored_as_clear_chat_response_without_citations(client, services):
    data, retrieval, coaching = services
    retrieval.retrieve.return_value = [passage(0.8)]
    coaching.generate.return_value = CoachingResult(PROVIDER_BLOCK_MESSAGE, [], blocked=True)
    response = client.post("/coach", json={"child_id": "child-1", "question": "Taking turns in play?"})
    assert response.status_code == 200
    assert response.json()["status"] == "safety_blocked"
    assert response.json()["answer"] == PROVIDER_BLOCK_MESSAGE
    assert response.json()["citations"] == []
    assert data.create_interaction.call_args.args[-1] == "safety_blocked"


@pytest.mark.parametrize("country", [None, "KE"])
def test_vaccination_notice_skips_retrieval_generation_and_preserves_country(client, services, country):
    data, retrieval, coaching = services
    response = client.post("/coach", json={"child_id": "child-1", "question": "Which vaccines are due?",
                                          **({"vaccination_country": country} if country else {})})
    assert response.status_code == 200
    assert response.json()["status"] == "vaccination_notice"
    assert response.json()["vaccination_country"] == "KE"
    assert len(response.json()["citations"]) == 2
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    assert data.create_interaction.call_args.args[-1] == "vaccination_notice"
    assert data.create_interaction.call_args.kwargs["vaccination_country"] == "KE"
    assert "Select a vaccination country" not in response.json()["answer"]


@pytest.mark.parametrize("question,domain", [
    ("How do vaccines work?", "who.int"),
    ("What side effects can vaccines have?", "unicef.org"),
])
def test_general_vaccine_education_returns_citation_without_model_call(client, services, question, domain, monkeypatch):
    monkeypatch.setattr("backend.services.vaccination.current_date", lambda: date(2026, 10, 28))
    data, retrieval, coaching = services
    response = client.post("/coach", json={"child_id": "child-1", "question": question})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "vaccination_notice"
    assert body["vaccination_country"] == "KE"
    assert body["citations"]
    assert domain in body["citations"][0]["source_url"]
    assert body["citations"][0]["pdf_page"] is None
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    data.create_interaction.assert_called_once()


@pytest.mark.parametrize("question", [
    "My baby has difficulty breathing after vaccination.",
    "My baby's face is swollen after vaccination.",
])
def test_danger_sign_precedes_vaccination_notice(client, services, question):
    _, retrieval, coaching = services
    response = client.post("/coach", json={"child_id": "child-1",
                                          "question": question,
                                          "vaccination_country": "KE"})
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_kenya_schedule_sources_are_saved_and_a_follow_up_keeps_the_topic(client, services):
    data, retrieval, coaching = services
    data.get_conversation.return_value = {"messages": []}
    data.save_conversation_turn.return_value = "answer-1"
    question = "Which vaccines at 9 months?"
    body = client.post("/coach", json={"child_id": "child-1", "conversation_id": "conversation-1",
                                      "question": question}).json()
    assert body["status"] == "vaccination_notice"
    assert "IPV 2" in body["answer"] and "TCV" in body["answer"]
    stored = data.save_conversation_turn.call_args.args[-1]
    assert stored["citations"] == body["citations"]
    assert stored["vaccination_country"] == "KE"
    assert len({source["passage_id"] for source in stored["citations"]}) == 2
    data.get_conversation.return_value = {"messages": [
        {"role": "user", "text": question}, {"role": "assistant", **stored},
    ]}
    follow_up = "What side effects can they have?"
    result = client.post("/coach", json={"child_id": "child-1", "conversation_id": "conversation-1",
                                        "question": follow_up}).json()
    assert result["status"] == "vaccination_notice"
    assert "Temporary soreness" in result["answer"]
    assert "9 months:" not in result["answer"]
    assert data.save_conversation_turn.call_args.args[3] == follow_up
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


@pytest.mark.parametrize("age,kind", [(24, None), (25, "age_out_of_scope")])
def test_schedule_respects_the_second_birthday_boundary(client, services, age, kind):
    data, retrieval, coaching = services
    data.get_child.return_value = {"age_months": age, "completed_months": age,
                                   "age_days": age * 30, "in_scope": age <= 24}
    body = client.post("/coach", json={"child_id": "child-1", "question": "Which vaccines are due?"}).json()
    assert body["response_kind"] == kind
    if kind:
        assert body["citations"] == []
        assert body["vaccination_country"] is None
    else:
        assert body["status"] == "vaccination_notice" and body["citations"]
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_schedule_rollback_never_falls_through_to_model_generated_dates(client, services, monkeypatch):
    monkeypatch.setattr("backend.services.vaccination.settings.KENYA_VACCINATION_SCHEDULE_ENABLED", False)
    _, retrieval, coaching = services
    body = client.post("/coach", json={"child_id": "child-1", "question": "Which vaccines at nine months?"}).json()
    assert body["status"] == "vaccination_notice"
    assert body["citations"] == []
    assert "TCV" not in body["answer"]
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_vaccine_schedule_uses_the_selected_profile_on_each_request(client, services):
    data, retrieval, coaching = services
    payload = {"child_id": "child-1", "question": "Which vaccines are due?"}
    data.get_child.return_value = {"age_months": 9.0, "completed_months": 9,
                                   "age_days": 274, "in_scope": True}
    older = client.post("/coach", json=payload).json()
    assert "9 months:" in older["answer"] and "At birth:" not in older["answer"]
    data.get_child.return_value = {"age_months": 0.5, "completed_months": 0,
                                   "age_days": 15, "in_scope": True}
    younger = client.post("/coach", json={**payload, "child_id": "child-2"}).json()
    assert "At birth:" in younger["answer"] and "9 months:" not in younger["answer"]
    assert younger["child_age_months"] == 0.5
    data.get_child.assert_called_with("user-1", "child-2")
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), float("inf")])
def test_gate_rejects_invalid_configuration(threshold):
    with pytest.raises(ValueError, match="RETRIEVAL_MIN_SCORE"):
        select_evidence([], threshold)


@pytest.fixture
def services(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "RETRIEVAL_MIN_SCORE", 0.50)
    monkeypatch.setattr(settings, "KENYA_VACCINATION_SCHEDULE_ENABLED", True)
    monkeypatch.setattr("backend.services.vaccination.current_date", lambda: date(2026, 10, 28))
    data, retrieval, coaching = MagicMock(), MagicMock(), MagicMock()
    data.get_child.return_value = {"age_months": 6.0, "completed_months": 6, "age_days": 183, "in_scope": True}
    data.create_interaction.return_value = "interaction-1"
    coaching.generate.return_value = CoachingResult("General information: Talk gently with your child.", [],
                                                    answer_basis="general_information")
    overrides = app.dependency_overrides.copy()
    app.dependency_overrides.update({
        require_authenticated_user: lambda: {"uid": "user-1"},
        get_caregiver_data_service: lambda: data,
        get_retrieval_service: lambda: retrieval,
        get_coaching_service: lambda: coaching,
    })
    yield data, retrieval, coaching
    app.dependency_overrides.clear()
    app.dependency_overrides.update(overrides)


@pytest.mark.parametrize("scores", [[], [0.49], [0.20, 0.48]])
def test_no_evidence_still_generates_and_saves_general_information(client, services, scores):
    data, retrieval, coaching = services
    retrieval.retrieve.return_value = [passage(score) for score in scores]
    response = client.post("/coach", json={"child_id": "child-1", "question": "How can I encourage communication at mealtime?"})
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["answer_basis"] == "general_information"
    assert response.json()["reference_status"] == "no_match"
    assert response.json()["citations"] == []
    assert coaching.generate.call_args.args[-1] == []
    assert data.create_interaction.call_args.args[-1] == "answered"
    assert data.create_interaction.call_args.kwargs["answer_basis"] == "general_information"


def test_only_eligible_evidence_reaches_generation(client, services):
    _, retrieval, coaching = services
    accepted = passage(0.7)
    retrieval.retrieve.return_value = [passage(0.3), accepted]
    coaching.generate.return_value = CoachingResult("Talk with your baby.", [accepted])
    response = client.post("/coach", json={"child_id": "child-1", "question": "How can I talk during feeding?"})
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert len(response.json()["citations"]) == 1
    assert coaching.generate.call_args.args[-1] == [accepted]


@pytest.mark.parametrize("question,kind", [
    ("What else can I try?", "clarification"),
    ("That didn't help.", "clarification"),
    ("car repair", "unrelated"),
    ("the child cant keep any food", "professional_referral"),
])
def test_fallback_kind_is_saved_without_generation(client, services, question, kind):
    data, retrieval, coaching = services
    retrieval.retrieve.return_value = []
    response = client.post("/coach", json={"child_id": "child-1", "question": question})
    assert response.status_code == 200
    assert response.json()["status"] == "no_evidence"
    assert response.json()["response_kind"] == kind
    assert response.json()["citations"] == []
    assert data.create_interaction.call_args.kwargs["response_kind"] == kind
    coaching.generate.assert_not_called()
    if kind == "unrelated" or "keep any food" in question:
        retrieval.retrieve.assert_not_called()


@pytest.mark.parametrize("question", ["Is that safe?", "How many times a day?", "She refuses it."])
def test_short_follow_up_keeps_subject_age_context_and_original_saved_message(client, services, question):
    data, retrieval, coaching = services
    topic = "My baby is 15 days old. I am feeding my baby."
    data.get_conversation.return_value = {"messages": [
        {"role": "user", "text": topic},
        {"role": "assistant", "text": "Talk gently during feeding.", "status": "answered"},
    ]}
    data.save_conversation_turn.return_value = "message-2"
    retrieval.retrieve.return_value = []
    response = client.post("/coach", json={"child_id": "child-1", "conversation_id": "conversation-1",
                                          "question": question})
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["child_age_months"] == pytest.approx(15 / 30.4375)
    if question == "How many times a day?":
        retrieval.retrieve.assert_not_called()
        assert coaching.generate.call_args.args[3][0].source_age_label == "0-6 months (upper bound excluded)"
    else:
        assert retrieval.retrieve.call_args.args[:2] == (f"{topic}\nFollow-up: {question}", 0)
        assert retrieval.retrieve.call_args.kwargs["child_age_days"] == 15
    coaching.generate.assert_called_once()
    assert coaching.generate.call_args.args[0] == question
    assert coaching.generate.call_args.kwargs["conversation_context"][0]["text"] == topic
    assert data.save_conversation_turn.call_args.args[3] == question


def test_follow_up_danger_check_uses_the_younger_child_age_even_if_storage_fails(client, services):
    data, retrieval, coaching = services
    data.get_conversation.return_value = {"messages": [
        {"role": "user", "text": "My 6-week-old baby feeds frequently."},
        {"role": "assistant", "text": "Watch their feeding cues.", "status": "answered"},
    ]}
    data.save_conversation_turn.side_effect = RuntimeError("Storage unavailable")
    response = client.post("/coach", json={"child_id": "child-1", "conversation_id": "conversation-1",
                                          "question": "She feels feverish.", "support_country": "KE"})
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "escalated"
    assert body["child_age_months"] == pytest.approx(42 / 30.4375)
    assert body["support_resources"]
    assert body["citations"]
    assert body["message_id"] is None
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


@pytest.mark.parametrize("reply,age,status", [("18 months", 18, "answered"), ("3 years", 36, "no_evidence")])
def test_age_clarification_then_short_age_reply_uses_the_right_child(client, services, reply, age, status):
    data, retrieval, coaching = services
    data.get_child.return_value = {"age_months": 3, "completed_months": 3, "age_days": 92, "in_scope": True}
    data.get_conversation.return_value = {"messages": []}
    data.save_conversation_turn.return_value = "message-2"
    question = "What food can I make for my toddler?"
    first = client.post("/coach", json={"child_id": "child-1", "conversation_id": "conversation-1",
                                       "question": question}).json()
    assert first["response_kind"] == "clarification"
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    data.get_conversation.return_value = {"messages": [
        {"role": "user", "text": question},
        {"role": "assistant", "text": first["answer"], "status": first["status"],
         "response_kind": first["response_kind"]},
    ]}
    body = client.post("/coach", json={"child_id": "child-1", "conversation_id": "conversation-1",
                                      "question": reply}).json()
    assert body["child_age_months"] == age
    assert body["status"] == status
    if status == "answered":
        assert coaching.generate.call_args.args[1] == age
        retrieval.retrieve.assert_not_called()
        assert coaching.generate.call_args.args[3][0].source_age_label == "12-25 months (upper bound excluded)"
        stored = data.save_conversation_turn.call_args.args[5]
        assert stored["subject_age_override"] == age
        assert stored["caregiver_request"] == question
        # The initial question can leave the bounded context; the stated age
        # remains attached to subsequent permitted turns, not to the profile.
        data.get_conversation.return_value = {"messages": [
            {"role": "user", "text": reply},
            {"role": "assistant", **stored},
        ]}
        later = client.post("/coach", json={"child_id": "child-1", "conversation_id": "conversation-1",
                                           "question": "What else can I try?"}).json()
        assert later["child_age_months"] == age
        assert later["status"] == "answered"
        retrieval.retrieve.assert_not_called()
        assert coaching.generate.call_args.args[3][0].source_age_label == "12-25 months (upper bound excluded)"
    else:
        assert body["response_kind"] == "age_out_of_scope"
        coaching.generate.assert_not_called()


def test_old_care_context_does_not_permit_a_new_unrelated_request(client, services):
    data, retrieval, coaching = services
    data.save_conversation_turn.return_value = "message-2"
    data.get_conversation.return_value = {"messages": [
        {"role": "user", "text": "I am feeding my baby."},
        {"role": "assistant", "text": "Talk gently.", "status": "answered"},
    ]}
    response = client.post("/coach", json={"child_id": "child-1", "conversation_id": "conversation-1",
                                          "question": "Write Python code to track my baby's feeds."})
    assert response.status_code == 200
    assert response.json()["response_kind"] == "unrelated"
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


@pytest.mark.parametrize("question,bad_answer", [
    ("I am feeding my baby.", "Give two tablespoons at every meal, twice a day."),
    ("My baby has a nappy rash.", "Apply zinc oxide cream twice a day."),
    ("My baby has reflux.", "Hold upright for twenty to thirty minutes. Contact a doctor."),
    ("My baby keeps waking during the night.", "Let your baby sleep on their front."),
])
def test_failed_care_answers_are_replaced_before_delivery_and_storage(client, services, question, bad_answer):
    data, retrieval, coaching = services
    retrieval.retrieve.return_value = []
    coaching.generate.return_value = CoachingResult(bad_answer, [])
    response = client.post("/coach", json={"child_id": "child-1", "question": question})
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "answered"
    assert body["answer"] != bad_answer
    assert body["answer_basis"] == "reference_assisted"
    assert body["citations"]
    assert all(c["source_url"].startswith(("https://www.nhs.uk/", "https://www.unicef.org/")) for c in body["citations"])
    assert data.create_interaction.call_args.args[4] == body["answer"]
    assert data.create_interaction.call_args.args[5] == body["citations"]
    coaching.generate.assert_called_once()


def test_vague_follow_up_after_unresolved_clarification_does_not_generate(client, services):
    data, retrieval, coaching = services
    data.save_conversation_turn.return_value = "message-2"
    data.get_conversation.return_value = {"messages": [
        {"role": "user", "text": "I am batting my baby."},
        {"role": "assistant", "text": "Do you mean bathing or something else?",
         "status": "no_evidence", "response_kind": "clarification"},
    ]}
    response = client.post("/coach", json={"child_id": "child-1", "conversation_id": "conversation-1",
                                          "question": "Is that safe?"})
    assert response.status_code == 200
    assert response.json()["response_kind"] == "clarification"
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_retrieval_failure_is_not_a_no_evidence_response(client, services):
    _, retrieval, coaching = services
    retrieval.retrieve.side_effect = TimeoutError("Connection timed out")
    response = client.post("/coach", json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["reference_status"] == "unavailable"
    assert response.json()["answer_basis"] == "general_information"
    coaching.generate.assert_called_once()


@pytest.mark.parametrize("error", [RuntimeError("request fragment: PRIVATE_CHILD_NAME"),
                                  ValueError("configuration includes PRIVATE_KEY_FRAGMENT")])
def test_generation_errors_do_not_expose_provider_text(client, services, caplog, error):
    _, retrieval, coaching = services
    retrieval.retrieve.return_value = []
    # A provider can echo only part of a prompt; exact full-question redaction
    # cannot protect this fragment. The endpoint must omit the description.
    error.message = "provider echoed PRIVATE_CHILD_NAME and PRIVATE_KEY_FRAGMENT"
    coaching.generate.side_effect = error
    response = client.post("/coach", json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code in {502, 503}
    for private_value in ("PRIVATE_CHILD_NAME", "PRIVATE_KEY_FRAGMENT"):
        assert private_value not in response.text
        assert private_value not in caplog.text


@pytest.mark.parametrize("answer,unknown_source", [
    ("Give 5 mg of medicine.", False),
    ("Talk softly [99].", False),
    ("Talk softly.", True),
])
def test_output_safety_replaces_answer_before_storage_and_delivery(client, services, caplog, answer, unknown_source):
    import logging

    data, retrieval, coaching = services
    accepted = passage(0.8)
    retrieval.retrieve.return_value = [accepted]
    returned = passage(0.8)
    if unknown_source:
        returned.passage_id = "invented-source"
    coaching.generate.return_value = CoachingResult(answer, [returned])
    with caplog.at_level(logging.INFO, logger="uvicorn.error.coaching_timing"):
        response = client.post("/coach", json={"child_id": "child-1", "question": "PRIVATE_QUESTION"})
    assert response.status_code == 200
    assert response.json()["status"] == "safety_blocked"
    assert response.json()["answer"] == SAFE_RESPONSE
    assert response.json()["citations"] == []
    saved = data.create_interaction.call_args.args
    assert saved[4:] == (SAFE_RESPONSE, [], "safety_blocked")
    assert "coaching_safety" in caplog.text
    assert "outcome=blocked" in caplog.text
    assert answer not in caplog.text
    assert "PRIVATE_QUESTION" not in caplog.text


@pytest.mark.parametrize("question", ["Play ideas", "How do vaccines work?"])
def test_older_profile_receives_age_notice_without_retrieval_or_generation(client, services, question):
    data, retrieval, coaching = services
    data.get_child.return_value = {"age_months": 24.1, "completed_months": 24,
                                   "age_days": 732, "in_scope": False}
    retrieval.retrieve.return_value = []
    response = client.post("/coach", json={"child_id": "child-1", "question": question})
    assert response.status_code == 200
    assert response.json()["status"] == "no_evidence"
    assert response.json()["response_kind"] == "age_out_of_scope"
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    data.create_interaction.assert_called_once()


def test_explicit_older_age_does_not_generate_using_younger_profile(client, services):
    _, retrieval, coaching = services
    retrieval.retrieve.return_value = []
    response = client.post("/coach", json={"child_id": "child-1", "question": "How can I support my 3-year-old's language?"})
    assert response.status_code == 200
    assert response.json()["child_age_months"] == 36
    assert response.json()["response_kind"] == "age_out_of_scope"
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


@pytest.mark.parametrize("age", [12, 24])
def test_explicit_in_range_age_overrides_profile_and_allows_general_information(client, services, age):
    _, retrieval, coaching = services
    retrieval.retrieve.return_value = []
    response = client.post("/coach", json={"child_id": "child-1", "question": f"How can I support my {age}-month-old's language?"})
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["child_age_months"] == age
    assert retrieval.retrieve.call_args.args[1] == age
    assert coaching.generate.call_args.args[1] == age


@pytest.mark.parametrize("question,expected_page", [
    ("My baby cannot breathe.", 45), ("My baby has green vomit.", None),
    ("My baby's lips have turned blue.", None),
    ("My baby has a rash that does not fade when I press it.", None),
])
def test_danger_report_bypasses_retrieval_and_generation(client, services, caplog, question, expected_page):
    import logging

    data, retrieval, coaching = services
    with caplog.at_level(logging.INFO, logger="uvicorn.error.coaching_timing"):
        response = client.post("/coach", json={"child_id": "child-1", "question": question})
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "escalated"
    assert body["safety"] == "escalate"
    assert body["answer"] == ESCALATION_MESSAGE
    assert body["citations"][0]["pdf_page"] == expected_page
    assert body["citations"][0]["source_url"].startswith("https://")
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    assert data.create_interaction.call_args.args[-1] == "escalated"
    assert "outcome=escalate" in caplog.text
    assert question not in caplog.text


def test_danger_report_for_aged_out_managed_profile_still_returns_referral(client, services):
    data, retrieval, coaching = services
    data.get_child.return_value = {"age_months": 25, "completed_months": 25,
                                   "age_days": 760, "in_scope": False}
    response = client.post("/coach", json={"child_id": "child-1", "question": "My baby is choking."})
    assert response.json()["status"] == "escalated"
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


@pytest.mark.parametrize("question", [
    "My baby is having blood in her eyes.", "My baby cannot breathe.",
])
@pytest.mark.parametrize("conversation_id", [None, "conversation-1"])
def test_child_emergency_in_kenya_includes_clickable_contacts_without_generation(client, services, question, conversation_id):
    data, retrieval, coaching = services
    data.save_conversation_turn.return_value = "answer-1"
    response = client.post("/coach", json={
        "child_id": "child-1", "question": question, "support_country": "KE",
        "conversation_id": conversation_id,
    })
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "escalated"
    emergency = [resource for resource in body["support_resources"] if resource["category"] == "emergency"]
    hospitals = [resource for resource in body["support_resources"] if resource["category"] == "hospital"]
    assert {resource["url"] for resource in emergency} == {"tel:999", "tel:112"}
    assert {resource["location"] for resource in hospitals} == {"Nairobi", "Eldoret", "Kisumu", "Mombasa"}
    assert any(resource["category"] == "ambulance" for resource in body["support_resources"])
    assert all(resource["source_url"] == "https://disastermanagement.go.ke/"
               for resource in emergency)
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    if conversation_id is None:
        assert data.create_interaction.call_args.args[-1] == "escalated"
    else:
        stored = data.save_conversation_turn.call_args.args[-1]
        assert stored["support_resources"] == body["support_resources"]
        assert body["conversation_id"] == conversation_id
        data.create_interaction.assert_not_called()


def test_medical_contacts_do_not_assume_kenya_when_country_is_not_supplied(client, services):
    response = client.post("/coach", json={
        "child_id": "child-1", "question": "My baby is having blood in her eyes.",
    })
    assert response.json()["status"] == "escalated"
    assert response.json()["support_resources"] == []


def test_unspecified_swallowed_button_gets_immediate_advice_and_verified_contacts(client, services):
    _, retrieval, coaching = services
    response = client.post("/coach", json={
        "child_id": "child-1", "question": "My baby swallowed a button", "support_country": "KE",
    })
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "escalated"
    assert body["answer"].startswith("Contact a health professional now")
    assert "?" not in body["answer"]
    assert "tel:999" in {resource["url"] for resource in body["support_resources"]}
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_referral_is_returned_even_when_interaction_storage_fails(client, services, caplog):
    import logging

    data, retrieval, coaching = services
    data.create_interaction.side_effect = RuntimeError("PRIVATE_DATABASE_DETAILS")
    with caplog.at_level(logging.WARNING, logger="uvicorn.error.coaching_timing"):
        response = client.post("/coach", json={"child_id": "child-1", "question": "My baby is choking."})
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
    assert response.json()["interaction_id"] is None
    assert response.json()["answer"] == ESCALATION_MESSAGE
    assert "persistence=failed" in caplog.text
    assert "PRIVATE_DATABASE_DETAILS" not in caplog.text
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


@pytest.mark.parametrize("question,status,safety", [
    ("I want to die.", "crisis_support", "escalate"),
    ("I am thinking about ending my life.", "crisis_support", "escalate"),
    ("I might hurt my baby.", "crisis_support", "escalate"),
    ("My partner shakes our child.", "crisis_support", "escalate"),
    ("I feel hopeless.", "caregiver_support", "not_flagged"),
    ("I feel depressed since giving birth.", "caregiver_support", "not_flagged"),
])
def test_caregiver_support_bypasses_generation_and_retrieval(client, services, caplog, question, status, safety):
    import logging

    data, retrieval, coaching = services
    with caplog.at_level(logging.INFO, logger="uvicorn.error.coaching_timing"):
        response = client.post("/coach", json={"child_id": "child-1", "question": question,
                                               "support_country": "KE"})
    assert response.status_code == 200
    assert response.json()["status"] == status
    assert response.json()["safety"] == safety
    assert response.json()["support_resources"]
    assert data.create_interaction.call_args.args[-1] == status
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    assert question not in caplog.text
    assert "coaching_caregiver_safety" in caplog.text


def test_unknown_location_has_general_support_without_assumed_contacts(client, services):
    response = client.post("/coach", json={"child_id": "child-1", "question": "I want to die."})
    assert response.json()["status"] == "crisis_support"
    assert response.json()["support_resources"] == []


def test_combined_child_danger_and_caregiver_crisis_preserves_both_paths(client, services):
    response = client.post("/coach", json={"child_id": "child-1",
        "question": "My baby cannot breathe and I want to die.", "support_country": "KE"})
    assert response.json()["status"] == "escalated"
    assert response.json()["support_resources"]
    assert response.json()["citations"]
    urls = [resource["url"] for resource in response.json()["support_resources"]]
    assert len(urls) == len(set(urls))


def test_caregiver_support_survives_storage_failure(client, services):
    data, retrieval, coaching = services
    data.create_interaction.side_effect = RuntimeError("Unavailable")
    response = client.post("/coach", json={"child_id": "child-1", "question": "I want to die.",
                                           "support_country": "KE"})
    assert response.status_code == 200
    assert response.json()["status"] == "crisis_support"
    assert response.json()["interaction_id"] is None
    assert response.json()["support_resources"]
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()


def test_timing_logs_show_stages_without_request_content(client, services, caplog):
    import logging

    _, retrieval, coaching = services
    accepted = passage(0.7, "PRIVATE_REFERENCE_TEXT")
    retrieval.retrieve.return_value = [accepted]
    coaching.generate.return_value = CoachingResult("PRIVATE_ANSWER_TEXT", [accepted])
    with caplog.at_level(logging.INFO, logger="uvicorn.error.coaching_timing"):
        response = client.post("/coach", json={"child_id": "child-1", "question": "PRIVATE_QUESTION_TEXT"})
    assert response.status_code == 200
    messages = "\n".join(record.getMessage() for record in caplog.records
                         if record.name == "uvicorn.error.coaching_timing")
    for stage in ("profile_lookup", "retrieval", "evidence_selection", "generation", "interaction_save"):
        assert f"stage={stage} event=started" in messages
        assert f"stage={stage} event=completed seconds=" in messages
    assert "stage=reported_total event=completed" in messages
    assert "passages=1 evidence=1 evidence_characters=" in messages
    for private in ("PRIVATE_QUESTION_TEXT", "PRIVATE_REFERENCE_TEXT", "PRIVATE_ANSWER_TEXT", "user-1", "child-1"):
        assert private not in messages


def test_gemini_unavailable_returns_busy_message_without_saving_answer(client, services):
    data, retrieval, coaching = services
    retrieval.retrieve.return_value = [passage(0.7)]
    coaching.generate.side_effect = genai_errors.ServerError(
        503, {"error": {"status": "UNAVAILABLE", "message": "Service unavailable"}},
    )
    response = client.post("/coach", json={"child_id": "child-1", "question": "Feeding ideas"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Something went wrong. Please try again."
    assert "status" not in response.json()
    coaching.generate.assert_called_once()
    data.create_interaction.assert_not_called()


def test_retrieval_unavailable_does_not_claim_gemini_is_busy(client, services):
    data, retrieval, coaching = services
    retrieval.retrieve.side_effect = genai_errors.ServerError(
        503, {"error": {"message": "Retrieval failure"}},
    )
    response = client.post("/coach", json={"child_id": "child-1", "question": "Feeding ideas"})
    assert response.status_code == 200
    assert response.json()["reference_status"] == "unavailable"
    coaching.generate.assert_called_once()
    data.create_interaction.assert_called_once()


def test_gemini_quota_error_returns_limit_message_without_saving_answer(client, services):
    data, retrieval, coaching = services
    retrieval.retrieve.return_value = [passage(0.7)]
    coaching.generate.side_effect = genai_errors.ClientError(
        429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}},
    )
    response = client.post("/coach", json={"child_id": "child-1", "question": "Feeding ideas"})
    assert response.status_code == 429
    assert response.json()["detail"] == "Please wait a little before trying again."
    assert "status" not in response.json()
    coaching.generate.assert_called_once()
    data.create_interaction.assert_not_called()


@pytest.mark.parametrize("code,expected", [(429, 429), (503, 503), (None, 502)])
def test_groq_failure_keeps_error_handling_without_saving_an_answer(client, services, code, expected):
    from backend.services.groq_client import GenerationProviderError

    data, retrieval, coaching = services
    coaching.provider = "groq"
    coaching.generate.side_effect = GenerationProviderError(code)
    response = client.post("/coach", json={"child_id": "child-1", "question": "Feeding ideas"})
    assert response.status_code == expected
    assert "answer" not in response.json()
    data.create_interaction.assert_not_called()
    data.save_conversation_turn.assert_not_called()
