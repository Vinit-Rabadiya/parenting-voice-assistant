"""Development wording checks, not a validated mental-health assessment."""

import pytest

from backend.services.crisis_safety import inspect_crisis
from backend.services.kenya_contacts import emergency_resources
from backend.schemas.coaching import SupportResource


@pytest.mark.parametrize("question,kind", [
    ("I want to die.", "crisis_support"),
    ("I am thinking about killing myself.", "crisis_support"),
    ("I am thinking about ending my life.", "crisis_support"),
    ("I don't want to live.", "crisis_support"),
    ("I feel suicidal.", "crisis_support"),
    ("I might shake my baby.", "crisis_support"),
    ("My partner is hitting my child.", "crisis_support"),
    ("My partner shakes our child.", "crisis_support"),
    ("My baby is being abused.", "crisis_support"),
    ("I think I have postpartum depression.", "caregiver_support"),
    ("I feel hopeless.", "caregiver_support"),
    ("I cannot cope.", "caregiver_support"),
    ("I can't bond with my baby.", "caregiver_support"),
    ("I feel depressed since giving birth.", "caregiver_support"),
])
def test_support_category_does_not_require_child_symptom_keywords(question, kind):
    result = inspect_crisis(question)
    assert result.kind == kind
    assert result.answer
    assert result.resources == ()


@pytest.mark.parametrize("question", [
    "I am not suicidal.", "I do not hurt my baby.",
    "I am not going to hurt myself.", "How can I prevent self-harm?",
    "I don't want to kill myself.",
    "I am not ending my life.",
    "My partner never shakes our child.",
    "I do not feel depressed since giving birth.",
    "What is postpartum depression?", "I am tired after feeding.",
    "How can I bond with my baby?", "I feel happy when my child smiles.",
])
def test_selected_negated_and_general_questions_do_not_trigger_support(question):
    assert inspect_crisis(question).kind is None


def test_negation_does_not_hide_a_separate_harm_report():
    assert inspect_crisis("I am not suicidal but I might shake my baby.").kind == "crisis_support"


def test_country_must_be_explicit_and_contacts_show_availability():
    for country in (None, "", "US", "unknown"):
        assert inspect_crisis("I want to die.", country).resources == ()
    result = inspect_crisis("I want to die.", "KE")
    assert all(r["country"] == "KE" for r in result.resources)
    assert all(r["verified_on"] and r["source_url"] for r in result.resources)
    assert any("Monday to Friday" in r["availability"] for r in result.resources)
    assert all(r["label"] != "988" for r in result.resources)


def test_child_safety_resources_are_not_mislabeled_as_general_counselling():
    result = inspect_crisis("I might hurt my baby.", "KE")
    assert any(r["service"] == "Kenya National Child Helpline" for r in result.resources)


def test_medical_directory_keeps_hospital_contacts_distinct_from_emergency_numbers():
    resources = emergency_resources("KE", include_hospitals=True)
    for resource in resources:
        SupportResource(**resource)
        assert resource["source_url"].startswith("https://")
    assert {r["label"] for r in resources if r["category"] == "emergency"} == {"999", "112"}
    assert all(r.get("location") for r in resources if r["category"] == "hospital")
    assert len({r["url"] for r in resources}) == len(resources)
    assert not any(r["category"] == "hospital" for r in emergency_resources("KE"))
    assert emergency_resources(None, include_hospitals=True) == ()


def test_contact_records_cannot_mutate_the_shared_directory():
    resources = emergency_resources("KE", include_hospitals=True)
    resources[0]["label"] = "changed"
    assert emergency_resources("KE")[0]["label"] == "999"
