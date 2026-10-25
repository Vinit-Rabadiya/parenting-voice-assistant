import pytest
from datetime import date
from pydantic import ValidationError

from backend.schemas.coaching import CoachingRequest
from backend.schemas.conversations import ConversationMessageResponse
from backend.services.vaccination import inspect_vaccination


@pytest.fixture(autouse=True)
def checked_source_date(monkeypatch):
    monkeypatch.setattr("backend.services.vaccination.current_date", lambda: date(2026, 10, 24))


@pytest.mark.parametrize("question", ["Which vaccines are due?",
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


def test_general_education_does_not_override_a_schedule_request():
    decision = inspect_vaccination("What is vaccination schedule at 9 months?")
    assert decision.reason == "references_pending_review"
    assert decision.source_url is None


@pytest.mark.parametrize("question", ["My child missed vaccines. Which doses today?",
                                     "Is my child allergic to this vaccine?",
                                     "What vaccine dosage should I give?"])
def test_individual_clinical_decisions_are_referred(question):
    assert inspect_vaccination(question).reason == "individual_assessment"


def test_normal_coaching_is_not_changed_by_kenya_scope():
    assert inspect_vaccination("How can I talk during feeding?") is None


@pytest.mark.parametrize("question,reason,domain", [
    ("How do vaccines work?", "general_purpose", "who.int"),
    ("Tell me about immunisation.", "general_purpose", "who.int"),
    ("What side effects can vaccines have?", "general_expected_effects", "unicef.org"),
])
def test_general_education_has_original_source_without_personal_schedule(question, reason, domain):
    decision = inspect_vaccination(question)
    assert decision.reason == reason
    assert domain in decision.source_url
    assert decision.source_title
    assert "mg" not in decision.answer


@pytest.mark.parametrize("question", [
    "My baby has a fever after vaccination. What side effects are expected?",
    "My child is crying after immunisation.",
    "What side effects after my child's missed vaccine doses?",
])
def test_reported_symptoms_and_individual_decisions_do_not_get_general_reassurance(question):
    assert inspect_vaccination(question).reason == "individual_assessment"


def test_general_education_requires_current_source_check(monkeypatch):
    monkeypatch.setattr("backend.services.vaccination.current_date", lambda: date(2027, 2, 1))
    assert inspect_vaccination("How do vaccines work?").reason == "references_pending_review"


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
