"""Known-pattern coverage; these checks do not establish clinical validity."""

from dataclasses import replace

import pytest

from backend.services.response_safety import inspect_response
from backend.services.retrieval import RetrievedPassage


def reference():
    return RetrievedPassage("p1", "Talk softly.", "Talk", "Source", 1,
                            "https://example.test", 0.8, "6-8 months", ["feeding"])


@pytest.mark.parametrize("answer,reason", [
    ("Give 5 mg of medicine.", "dose_expression"),
    ("Use antibiotics for the infection.", "medication_instruction"),
    ("Your baby has pneumonia.", "diagnostic_claim"),
    ("Your child is 5 years old.", "conflicting_age_claim"),
    ("Talk softly [9].", "invalid_citation_marker"),
    ("Read https://untrusted.example/advice", "model_generated_link"),
    (" ", "empty_answer"),
    ("Do not give medicine. Give antibiotics instead.", "medication_instruction"),
    ("Do not give medicine, give antibiotics instead.", "medication_instruction"),
    ("Don't give a toy, use antibiotics instead.", "medication_instruction"),
    ("Give medicine, never use antibiotics.", "medication_instruction"),
    ("Shake your baby to stop the crying.", "harmful_child_instruction"),
    ("Hit the child.", "harmful_child_instruction"),
    ("It is completely normal for your child to refuse food.", "blanket_reassurance"),
    ("This is perfectly normal.", "blanket_reassurance"),
    ("There is nothing to worry about.", "blanket_reassurance"),
])
def test_known_prohibited_output_is_blocked(answer, reason):
    passage = reference()
    decision = inspect_response(answer, [passage], [passage], 6)
    assert decision.blocked
    assert reason in decision.reasons


@pytest.mark.parametrize("answer", [
    "Talk and sing to your baby.",
    "Give your baby time to respond to your sounds.",
    "Use a soft ball for play.",
    "I cannot diagnose your baby. Contact a health professional.",
    "Do not give medicine without advice from a qualified health professional.",
    "Never use antibiotics without professional advice.",
    "Don\u2019t give medicine without professional advice.",
    "Talk softly [1].",
    "Never shake your baby.",
    "Shake a rattle for your baby.",
    "Food preferences can vary. I cannot assess your child's health here.",
])
def test_benign_wording_and_direct_medication_refusals_are_not_blocked(answer):
    passage = reference()
    assert not inspect_response(answer, [passage], [passage], 6).blocked


def test_matching_id_with_modified_url_is_not_trusted():
    passage = reference()
    altered = replace(passage, source_url="https://untrusted.example")
    assert "invalid_source_provenance" in inspect_response("Talk softly.", [altered], [passage], 6).reasons


def test_unknown_passage_and_out_of_scope_age_are_blocked():
    passage = reference()
    decision = inspect_response("Talk softly.", [replace(passage, passage_id="unknown")], [passage], 25)
    assert "invalid_source_provenance" in decision.reasons
    assert "profile_out_of_scope" in decision.reasons


def test_known_conservative_measurement_rule_is_explicit():
    passage = reference()
    decision = inspect_response("The container holds 200 ml of water.", [passage], [passage], 6)
    # This documents an intentional false-positive risk, not a clinical dose judgment.
    assert "dose_expression" in decision.reasons


def test_supplied_source_id_with_changed_text_is_blocked():
    passage = reference()
    altered = replace(passage, text="Unverified replacement text.")
    assert "invalid_source_provenance" in inspect_response("Talk softly.", [altered], [passage], 6).reasons


def test_age_claim_in_years_is_compared_in_months():
    passage = reference()
    assert not inspect_response("Your child is 2 years old.", [passage], [passage], 24).blocked
    assert "conflicting_age_claim" in inspect_response("Your child is 2 years old.", [passage], [passage], 6).reasons


def test_numbered_reference_must_also_have_a_returned_source_card():
    first = reference()
    second = replace(first, passage_id="p2")
    decision = inspect_response("Talk softly [1].", [second], [first, second], 6)
    assert "invalid_citation_marker" in decision.reasons
