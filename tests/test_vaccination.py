import pytest
from pydantic import ValidationError

from backend.schemas.coaching import CoachingRequest
from backend.schemas.conversations import ConversationMessageResponse
from backend.services.vaccination import inspect_vaccination


@pytest.mark.parametrize("question", ["Which vaccines are due?", "Tell me about immunisation.",
                                     "What does BCG protect against?", "What is pentavalent?"])
def test_vaccination_uses_kenya_scope_without_asking_for_country(question):
    decision = inspect_vaccination(question)
    assert decision.reason == "references_pending_review"
    assert "Kenya-specific" in decision.answer
    assert "Select a vaccination country" not in decision.answer


def test_kenya_does_not_enable_unapproved_schedule_answers():
    decision = inspect_vaccination("Which vaccines at nine months?")
    assert decision.reason == "references_pending_review"
    assert "cannot confirm" in decision.answer


@pytest.mark.parametrize("question", ["My child missed vaccines. Which doses today?",
                                     "Is my child allergic to this vaccine?",
                                     "What vaccine dosage should I give?"])
def test_individual_clinical_decisions_are_referred(question):
    assert inspect_vaccination(question).reason == "individual_assessment"


def test_normal_coaching_is_not_changed_by_kenya_scope():
    assert inspect_vaccination("How can I talk during feeding?") is None


def test_support_country_is_not_used_as_vaccination_country():
    request = CoachingRequest(child_id="child", question="Which vaccines?")
    assert request.support_country is None
    assert request.vaccination_country == "KE"


@pytest.mark.parametrize("country", ["invalid", "OTHER", "US", None])
def test_unsupported_vaccination_country_value_is_rejected(country):
    with pytest.raises(ValidationError):
        CoachingRequest(child_id="child", question="Which vaccines?", vaccination_country=country)


def test_history_contract_retains_selected_vaccination_country():
    message = ConversationMessageResponse(id="answer", role="assistant", text="Clinic information",
                                          created_at="2026-10-22T12:00:00Z",
                                          status="vaccination_notice", vaccination_country="KE")
    assert message.model_dump()["vaccination_country"] == "KE"
