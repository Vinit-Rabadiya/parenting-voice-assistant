"""Child danger-sign tests share the version-controlled evaluation dataset."""

import pytest

from backend.services.input_safety import inspect_input
from scripts.evaluate_safety import load_cases


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["id"])
def test_shared_safety_case(case):
    decision = inspect_input(case["question"], case["completed_months"])
    assert decision.escalate == case["should_escalate"]
    if decision.escalate:
        assert decision.citations


def test_fever_age_boundary_uses_completed_calendar_months():
    assert inspect_input("My baby has a fever.", 2).escalate
    assert not inspect_input("My baby has a fever.", 3).escalate


def test_smart_apostrophes_and_capitalization():
    assert inspect_input("MY BABY WON\u2019T FEED", 6).escalate


@pytest.mark.parametrize("question", [
    "My baby has green vomit.", "My baby is vomiting blood.",
    "My child's vomit looks green.", "My baby has blood in her vomit.",
    "My baby's lips have turned blue.", "My baby has grey lips.",
    "My baby has a rash that does not fade when I press it.",
])
def test_additional_source_backed_danger_reports(question):
    decision = inspect_input(question, 6)
    assert decision.escalate
    assert decision.citations


@pytest.mark.parametrize("question", [
    "My baby has no green vomit.", "My baby is not vomiting blood.",
    "My baby's lips are not blue.", "My baby has no grey lips.",
    "My baby has a rash that fades when pressed.", "My baby has green clothes.",
])
def test_additional_rules_do_not_escalate_denied_or_unrelated_descriptions(question):
    assert not inspect_input(question, 6).escalate


@pytest.mark.parametrize("question", [
    "My baby is not having a seizure.",
    "My child does not have a fever.",
    "My baby is not feeding poorly.",
    "My baby is not breathing fast.",
])
def test_additional_negated_phrases_do_not_trigger_by_themselves(question):
    assert not inspect_input(question, 1).escalate


def test_non_emergency_clause_does_not_hide_another_danger_sign():
    assert inspect_input("My baby is not breathing fast but is choking.", 1).escalate


@pytest.mark.parametrize("question", [
    "My baby cannot keep his milk down.",
    "She can't keep her feeds down.",
    "My child cannot keep any of their fluids down.",
])
def test_fluid_retention_wording_preserves_urgent_routing(question):
    assert "cannot_keep_fluids" in inspect_input(question, 6).reasons


@pytest.mark.parametrize("question", [
    "My baby is having blood in her eyes.",
    "My baby's eye is bleeding.",
    "Blood is coming from my baby's eye.",
    "My child has bloody tears.",
])
def test_eye_bleeding_reports_require_urgent_assessment(question):
    decision = inspect_input(question, 2)
    assert decision.escalate
    assert "eye_bleeding" in decision.reasons
    assert any(source["source_url"] == "https://www.nhs.uk/conditions/eye-injuries/"
               for source in decision.citations)


@pytest.mark.parametrize("question", [
    "My baby has no blood in her eyes.",
    "My baby's eye is not bleeding.",
    "My baby has a red eye.",
    "How can I prevent blood in my baby's eyes?",
])
def test_eye_rule_does_not_treat_redness_or_denied_bleeding_as_active_bleeding(question):
    assert not inspect_input(question, 2).escalate


@pytest.mark.parametrize("question", [
    "My baby is bleeding heavily.", "My child's cut won't stop bleeding.",
    "My baby swallowed bleach.", "My baby drank kerosene.",
    "My child was given too much medicine.", "My baby swallowed a button battery.",
    "My child swallowed two magnets.", "My baby has been scalded by hot water.",
    "My baby has a chemical burn.",
])
def test_other_source_backed_emergencies_bypass_ordinary_coaching(question):
    decision = inspect_input(question, 6)
    assert decision.escalate
    assert decision.citations


@pytest.mark.parametrize("question", [
    "My baby is not bleeding heavily.", "My baby has not swallowed a battery.",
    "My baby is not scalded.", "I feel burned out after caring for my baby.",
    "My baby drank milk.", "My baby took the prescribed medicine.",
    "How can I prevent my baby getting burned?",
])
def test_new_emergency_rules_do_not_replace_ordinary_care_or_denied_reports(question):
    assert not inspect_input(question, 6).escalate


@pytest.mark.parametrize("object_name", ["a button", "a small coin", "a plastic bead", "a toy part", "an object"])
def test_swallowed_object_gets_immediate_advice_without_waiting_for_clarification(object_name):
    decision = inspect_input(f"My baby swallowed {object_name}.", 2)
    assert decision.reasons == ("swallowed_object",)
    assert decision.answer.startswith("Contact a health professional now")
    assert "?" not in decision.answer
    assert "If your baby is choking" in decision.answer


def test_explicit_battery_or_additional_danger_keeps_immediate_referral():
    from backend.services.input_safety import ESCALATION_MESSAGE

    assert inspect_input("My baby swallowed a button battery.", 2).answer == ESCALATION_MESSAGE
    assert inspect_input("My baby swallowed a button and is choking.", 2).answer == ESCALATION_MESSAGE
    assert not inspect_input("My baby has not swallowed a button.", 2).escalate


@pytest.mark.parametrize("reading", ["38C", "38.2 C", "38,2 C", "38 degrees Celsius", "38°C"])
def test_young_infant_explicit_celsius_readings(reading):
    decision = inspect_input(f"My baby's temperature is {reading}", 2)
    assert "young_infant_temperature" in decision.reasons


@pytest.mark.parametrize("question,months", [
    ("My baby's temperature is 37.9C", 2),
    ("My baby's temperature is 38C", 3),
    ("My baby's temperature is 100.4F", 2),
    ("My baby's temperature is 38", 2),
    ("My baby's bath water is 38C", 2),
    ("My baby's room is 38C", 2),
    ("My baby's temperature is below 38C", 2),
    ("My baby's temperature is not 38C", 2),
])
def test_numeric_rule_does_not_infer_units_or_apply_to_other_ages_and_objects(question, months):
    assert "young_infant_temperature" not in inspect_input(question, months).reasons


@pytest.mark.parametrize("question,urgent", [
    ("My baby's lips are swollen after vaccination.", True),
    ("My baby has swelling of the face.", True),
    ("My child's throat has become swollen.", True),
    ("My baby has no swelling of the face.", False),
    ("My baby's lips are not swollen.", False),
    ("My baby has soreness at the injection site.", False),
])
def test_facial_airway_swelling_is_distinct_from_injection_site_soreness(question, urgent):
    decision = inspect_input(question, 6)
    assert decision.escalate == urgent
    if urgent:
        assert decision.reasons == ("facial_airway_swelling",)
        assert decision.citations[0]["pdf_page"] == 2
