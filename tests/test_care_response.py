import pytest

from backend.services.care_response import clearly_unrelated, missing_evidence_response
from backend.services.care_response import feeding_concern_response
from backend.services.care_response import professional_assessment_response


@pytest.mark.parametrize("message", [
    "I am feeding my baby", "Packing for an outing with my toddler",
    "I am changing my baby's clothes", "My child is turning one",
])
def test_relevant_statements_receive_an_honest_next_step(message):
    response = missing_evidence_response(message)
    assert response.kind == "insufficient_references"
    assert not clearly_unrelated(message)


@pytest.mark.parametrize("message", ["car repair", "repair my car", "write python code",
                                      "What is the weather forecast tomorrow?", "How do I fix my internet router?",
                                      "Please reset the wifi", "Configure my router"])
def test_explicit_unrelated_requests_are_distinct(message):
    assert clearly_unrelated(message)
    assert missing_evidence_response(message).kind == "unrelated"


def test_mixed_baby_care_request_is_not_rejected_by_unrelated_keyword():
    assert not clearly_unrelated("Keep my baby safe while I repair my car")


def test_unknown_message_is_clarified_not_declared_unrelated():
    assert missing_evidence_response("What should I do?").kind == "clarification"


def test_follow_up_without_permitted_context_asks_for_the_topic():
    assert missing_evidence_response("what else?", unresolved_follow_up=True).kind == "clarification"


@pytest.mark.parametrize("message", ["My baby has a rash", "fever", "My child is losing skills"])
def test_missing_health_evidence_is_not_reassurance(message):
    response = missing_evidence_response(message)
    assert response.kind == "professional_referral"
    assert "does not mean it is safe to wait" in response.answer


@pytest.mark.parametrize("message", ["the child cant keep any food", "My baby can't keep food down", "My baby cannot keep milk down", "My child cannot keep his food down"])
def test_feed_retention_concern_gets_professional_referral(message):
    assert feeding_concern_response(message).kind == "professional_referral"


@pytest.mark.parametrize("message", ["My baby can keep food down", "How can I keep food fresh for my baby?"])
def test_ordinary_food_messages_do_not_match_retention_concern(message):
    assert feeding_concern_response(message) is None


@pytest.mark.parametrize("message", [
    "Can you diagnose why my child is not talking?",
    "Tell me what medicine dose my baby needs.",
    "Calculate a dose for my child.",
])
def test_individual_clinical_requests_are_distinct_from_general_information(message):
    assert professional_assessment_response(message).kind == "professional_referral"


def test_possible_explanations_are_not_automatically_treated_as_diagnosis_requests():
    assert professional_assessment_response("What might contribute to hard stools in a toddler?") is None
