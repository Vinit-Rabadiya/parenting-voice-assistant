from unittest.mock import MagicMock
from google.genai import errors as genai_errors

import pytest

from backend.api.dependencies import get_caregiver_data_service, get_coaching_service, get_retrieval_service
from backend.core.security import require_authenticated_user
from backend.main import app
from backend.services.coaching import CoachingResult
from backend.services.evidence import select_evidence
from backend.services.retrieval import RetrievedPassage
from backend.services.response_safety import SAFE_RESPONSE
from backend.services.input_safety import ESCALATION_MESSAGE


def passage(score: float, text: str = "Talk with your baby during feeding.") -> RetrievedPassage:
    return RetrievedPassage("p1", text, "Feeding conversation", "Reference", 1,
                            "https://example.test/reference", score, "6-8 months", ["feeding"])


def test_gate_keeps_boundary_and_rejects_invalid_or_empty_evidence():
    accepted = passage(0.50)
    assert select_evidence([passage(0.49), passage(float("nan")), passage(float("inf")),
                            passage(0.9, " "), accepted], 0.50) == [accepted]


@pytest.mark.parametrize("country", [None, "KE"])
def test_vaccination_notice_skips_retrieval_generation_and_preserves_country(client, services, country):
    data, retrieval, coaching = services
    response = client.post("/coach", json={"child_id": "child-1", "question": "Which vaccines are due?",
                                          **({"vaccination_country": country} if country else {})})
    assert response.status_code == 200
    assert response.json()["status"] == "vaccination_notice"
    assert response.json()["vaccination_country"] == "KE"
    assert response.json()["citations"] == []
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    assert data.create_interaction.call_args.args[-1] == "vaccination_notice"
    assert data.create_interaction.call_args.kwargs["vaccination_country"] == "KE"
    assert "Select a vaccination country" not in response.json()["answer"]


def test_danger_sign_precedes_vaccination_notice(client, services):
    _, retrieval, coaching = services
    response = client.post("/coach", json={"child_id": "child-1",
                                          "question": "My baby has difficulty breathing after vaccination.",
                                          "vaccination_country": "KE"})
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
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
    data, retrieval, coaching = MagicMock(), MagicMock(), MagicMock()
    data.get_child.return_value = {"age_months": 6.0, "completed_months": 6, "age_days": 183, "in_scope": True}
    data.create_interaction.return_value = "interaction-1"
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
def test_no_evidence_skips_generation_and_saves_outcome(client, services, scores):
    data, retrieval, coaching = services
    retrieval.retrieve.return_value = [passage(score) for score in scores]
    response = client.post("/coach", json={"child_id": "child-1", "question": "Unsupported question"})
    assert response.status_code == 200
    assert response.json()["status"] == "no_evidence"
    assert response.json()["citations"] == []
    coaching.generate.assert_not_called()
    assert data.create_interaction.call_args.args[-1] == "no_evidence"


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
    ("I am feeding my baby", "insufficient_references"),
    ("My baby has a rash", "professional_referral"),
    ("What should I do?", "clarification"),
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


def test_retrieval_failure_is_not_a_no_evidence_response(client, services):
    _, retrieval, coaching = services
    retrieval.retrieve.side_effect = TimeoutError("Connection timed out")
    response = client.post("/coach", json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code == 502
    assert "status" not in response.json()
    coaching.generate.assert_not_called()


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


def test_out_of_scope_profile_never_reaches_retrieval_or_generation(client, services):
    data, retrieval, coaching = services
    data.get_child.return_value = {"age_months": 24.1, "completed_months": 24,
                                   "age_days": 732, "in_scope": False}
    response = client.post("/coach", json={"child_id": "child-1", "question": "Play ideas"})
    assert response.status_code == 422
    retrieval.retrieve.assert_not_called()
    coaching.generate.assert_not_called()
    data.create_interaction.assert_not_called()


def test_danger_report_bypasses_retrieval_and_generation(client, services, caplog):
    import logging

    data, retrieval, coaching = services
    question = "My baby cannot breathe."
    with caplog.at_level(logging.INFO, logger="uvicorn.error.coaching_timing"):
        response = client.post("/coach", json={"child_id": "child-1", "question": question})
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "escalated"
    assert body["safety"] == "escalate"
    assert body["answer"] == ESCALATION_MESSAGE
    assert body["citations"][0]["pdf_page"] == 45
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
    assert response.json()["detail"] == "The coaching service is temporarily busy. Please try again later."
    assert "status" not in response.json()
    coaching.generate.assert_called_once()
    data.create_interaction.assert_not_called()


def test_retrieval_unavailable_does_not_claim_gemini_is_busy(client, services):
    data, retrieval, coaching = services
    retrieval.retrieve.side_effect = genai_errors.ServerError(
        503, {"error": {"message": "Retrieval failure"}},
    )
    response = client.post("/coach", json={"child_id": "child-1", "question": "Feeding ideas"})
    assert response.status_code == 502
    assert "busy" not in response.json()["detail"]
    coaching.generate.assert_not_called()
    data.create_interaction.assert_not_called()


def test_gemini_quota_error_returns_limit_message_without_saving_answer(client, services):
    data, retrieval, coaching = services
    retrieval.retrieve.return_value = [passage(0.7)]
    coaching.generate.side_effect = genai_errors.ClientError(
        429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}},
    )
    response = client.post("/coach", json={"child_id": "child-1", "question": "Feeding ideas"})
    assert response.status_code == 429
    assert response.json()["detail"] == "The coaching service request limit has been reached. Please try again later."
    assert "status" not in response.json()
    coaching.generate.assert_called_once()
    data.create_interaction.assert_not_called()
