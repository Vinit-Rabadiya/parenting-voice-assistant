import pytest
from datetime import date
from pydantic import ValidationError

from backend.schemas.coaching import CoachingRequest
from backend.schemas.conversations import ConversationMessageResponse
from backend.services.vaccination import GENERAL_CHECKED_ON, inspect_vaccination


@pytest.fixture(autouse=True)
def checked_source_date(monkeypatch):
    monkeypatch.setattr("backend.services.vaccination.current_date", lambda: GENERAL_CHECKED_ON)
    monkeypatch.setattr("backend.services.vaccination.settings.KENYA_VACCINATION_SCHEDULE_ENABLED", True)


def test_vaccination_uses_kenya_scope_without_asking_for_country():
    decision = inspect_vaccination("Which vaccines are due?")
    assert decision.reason == "routine_schedule"
    assert "Kenya's routine" in decision.answer
    assert "do not show which doses" in decision.answer
    assert "clinic" in decision.answer
    assert "Select a vaccination country" not in decision.answer


def test_nine_month_schedule_includes_new_programme_updates():
    decision = inspect_vaccination("Which vaccines at nine months?")
    assert decision.reason == "routine_schedule"
    assert "IPV 2" in decision.answer
    assert "typhoid conjugate vaccine (TCV)" in decision.answer
    assert "Measles-rubella (MR) 1" in decision.answer
    assert "eligible programme areas" in decision.answer
    assert "6 weeks:" not in decision.answer


def test_general_education_does_not_override_a_schedule_request():
    decision = inspect_vaccination("What is vaccination schedule at 9 months?")
    assert decision.reason == "routine_schedule"
    assert decision.sources


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
    assert any(domain in source.url for source in decision.sources)
    assert all(source.title for source in decision.sources)
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
    assert inspect_vaccination("How do vaccines work?") is None


@pytest.mark.parametrize("question,expected", [
    ("What does BCG protect against?", "tuberculosis"),
    ("What is pentavalent?", "hepatitis B"),
    ("What is PCV?", "pneumonia"),
    ("What is TCV?", "typhoid fever"),
    ("What is the yellow fever vaccine for?", "designated risk areas"),
    ("Tell me about the malaria vaccine.", "insecticide-treated mosquito net"),
])
def test_named_vaccine_education_has_source_links(question, expected):
    decision = inspect_vaccination(question)
    assert decision.reason == "vaccine_purpose"
    assert expected in decision.answer
    assert decision.sources


@pytest.mark.parametrize("question,expected,excluded", [
    ("Which vaccines at birth?", "BCG", "rotavirus 3"),
    ("What vaccines at six weeks?", "rotavirus 1", "IPV 2"),
    ("Which vaccines at 10 weeks?", "rotavirus 2", "rotavirus 3"),
    ("What vaccines at 14 weeks?", "rotavirus 3", "IPV 2"),
    ("What vaccines at 18 months?", "MR 2", "MR) 1"),
    ("Which vaccines at two years?", "Malaria vaccine 4", "rotavirus 3"),
])
def test_week_and_month_visits_are_not_interchanged(question, expected, excluded):
    answer = inspect_vaccination(question).answer
    assert expected in answer
    assert excluded not in answer
    assert "confirm the next appointment" in answer


def test_full_schedule_and_product_difference_do_not_omit_or_add_doses():
    answer = inspect_vaccination("Full Kenya vaccination schedule from birth to 24 months").answer
    for label in ["At birth:", "6 weeks:", "10 weeks:", "14 weeks:", "9 months:", "18 months:", "24 months (second birthday):"]:
        assert label in answer
    rotarix = inspect_vaccination("How many doses of Rotarix?")
    assert rotarix.reason == "vaccine_purpose"
    assert "Rotarix uses a two-dose series" in rotarix.answer
    assert "check the vaccine product" in rotarix.answer
    polio = inspect_vaccination("When is IPV given?").answer
    assert "14 weeks:" in polio and "9 months:" in polio
    assert "6 weeks:" not in polio


@pytest.mark.parametrize("age,expected,excluded", [
    (0.5, ["At birth:", "6 weeks:"], "9 months:"),
    (9.0, ["9 months:", "18 months:"], "At birth:"),
    (20.0, ["18 months:", "24 months (second birthday):"], "6 weeks:"),
])
def test_schedule_uses_profile_age_without_requiring_it_in_the_message(age, expected, excluded):
    answer = inspect_vaccination("Which vaccines are due?", age).answer
    assert "around your child's age" in answer
    assert all(label in answer for label in expected)
    assert excluded not in answer
    assert "do not show which doses" in answer


def test_explicit_age_and_full_overview_take_priority_over_the_profile_age():
    age_specific = inspect_vaccination("Which vaccines at 9 months?", 0.5).answer
    assert "9 months:" in age_specific and "At birth:" not in age_specific
    overview = inspect_vaccination("Show the full vaccination schedule", 9).answer
    assert "At birth:" in overview and "24 months (second birthday):" in overview
    named = inspect_vaccination("When is IPV given?", 9).answer
    assert "14 weeks:" in named and "9 months:" in named


@pytest.mark.parametrize("checked_on", [date(2026, 10, 29), date(2026, 7, 29)])
def test_stale_or_future_schedule_checks_withdraw_specific_answers(monkeypatch, checked_on):
    monkeypatch.setattr("backend.services.vaccination.SCHEDULE_CHECKED_ON", checked_on)
    for question in ["Which vaccines at 9 months?", "What is TCV?"]:
        decision = inspect_vaccination(question)
        assert decision.reason == "schedule_unavailable"
        assert decision.sources == ()
        assert "TCV" not in decision.answer


def test_schedule_switch_withdraws_facts_without_disabling_general_education(monkeypatch):
    monkeypatch.setattr("backend.services.vaccination.settings.KENYA_VACCINATION_SCHEDULE_ENABLED", False)
    assert inspect_vaccination("Which vaccines at 9 months?").reason == "schedule_unavailable"
    assert inspect_vaccination("What is BCG?").reason == "schedule_unavailable"
    assert inspect_vaccination("How do vaccines work?").reason == "general_purpose"


def test_follow_up_uses_current_question_for_effects_and_individual_symptoms():
    topic = "Which vaccines at nine months?\nFollow-up: What side effects can they have?"
    assert inspect_vaccination("What side effects can they have?", topic=topic).reason == "general_expected_effects"
    assert inspect_vaccination("My baby has a fever. Is that a side effect?", topic=topic).reason == "individual_assessment"
    assert inspect_vaccination("What does that mean?", topic="What is TCV?").reason == "vaccine_purpose"


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
