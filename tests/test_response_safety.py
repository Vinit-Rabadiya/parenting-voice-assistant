"""Known-pattern coverage; these checks do not establish clinical validity."""

from dataclasses import replace

import pytest

from backend.services.response_safety import inspect_response
from backend.services.retrieval import RetrievedPassage
from backend.services.care_guidance import get_care_guidance
from backend.services.coaching import CoachingResult, PROVIDER_BLOCK_MESSAGE
from backend.services.response_safety import review_coaching_result


def reference():
    return RetrievedPassage("p1", "Talk softly.", "Talk", "Source", 1,
                            "https://example.test", 0.8, "6-8 months", ["feeding"])


@pytest.mark.parametrize("answer,reason", [
    ("Give 5 mg of medicine.", "dose_expression"),
    ("Use antibiotics for the infection.", "medication_instruction"),
    ("Your baby has pneumonia.", "diagnostic_claim"),
    ("Your child is 5 years old.", "conflicting_age_claim"),
    ("Talk softly [9].", "invalid_citation_marker"),
    ("Talk softly [1, 9].", "invalid_citation_marker"),
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


def test_unknown_passage_is_blocked_for_older_children_too():
    passage = reference()
    decision = inspect_response("Talk softly.", [replace(passage, passage_id="unknown")], [passage], 25)
    assert "invalid_source_provenance" in decision.reasons
    assert "profile_out_of_scope" in decision.reasons


def test_general_information_can_pass_without_source_cards():
    assert not inspect_response("General information: Read a picture book together.", [], [], 12).blocked
    assert inspect_response("Give 5 mg of medicine.", [], [], 36).blocked


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
    assert "conflicting_age_claim" in inspect_response("Your child is 25 months old.", [passage], [passage], 24).reasons


def test_numbered_reference_must_also_have_a_returned_source_card():
    first = reference()
    second = replace(first, passage_id="p2")
    decision = inspect_response("Talk softly [1].", [second], [first, second], 6)
    assert "invalid_citation_marker" in decision.reasons


@pytest.mark.parametrize("question,age,answer,reason", [
    ("What food can I make for my toddler?", 18, "Offer soft beans. Aim for three meals and two snacks daily.", "unrequested_feeding_schedule"),
    ("What food can I make for my toddler?", 18, "Offer soft foods. Talk with your toddler and name foods.", "unrequested_interaction_activity"),
    ("I am feeding my baby.", 6, "Give two tablespoons per meal, twice a day.", "unrequested_feeding_amount"),
    ("I am feeding my baby.", 6, "Start offering porridge and mashed vegetables.", "missing_first_food_readiness"),
    ("I am feeding my baby.", 6, "Try offering finely minced family foods like rice or fish. Keep your baby upright.", "missing_first_food_readiness"),
    ("My baby has a nappy rash.", 9, "Apply a thick layer of zinc oxide cream. Ask a doctor if worried.", "treatment_product_selection"),
    ("My baby has a nappy rash.", 9, "Applying a thick layer of a barrier ointment can help. Ask a doctor if fever occurs.", "treatment_product_selection"),
    ("Some milk comes back up after feeds.", 3, "Hold your baby upright for thirty minutes. Ask a doctor if worried.", "missing_sleep_position_precaution"),
    ("My baby has reflux.", 3, "Hold upright for 20 to 30 minutes, then sleep flat on the back. Ask a doctor if worried.", "unsupported_care_duration"),
    ("My baby has reflux.", 3, "Try smaller feeds more frequently. Sleep flat on the back. Ask a doctor if worried.", "individual_feeding_change"),
    ("My baby has a nappy rash.", 9, "Clean gently with water and dry the skin.", "missing_assessment_boundary"),
    ("My baby keeps waking during the night.", 3, "Dim the lights and sing softly.", "missing_sleep_position_precaution"),
    ("How can I help sore skin around my child's nappy area?", 18,
     "Clean gently. Ask a doctor if it gets worse.", "missing_rash_fever_boundary"),
    ("How can I make bedtime calmer?", 18,
     "Begin a story thirty minutes before sleep.", "unrequested_sleep_timing"),
])
def test_failed_care_answer_is_replaced_with_permitted_source_text(question, age, answer, reason):
    guidance = get_care_guidance(question, age)
    result = CoachingResult(answer, guidance.references)
    reviewed, decision = review_coaching_result(result, guidance.references, age, question)
    assert not decision.blocked
    assert decision.replaced_with_basic_care
    assert reason in decision.reasons
    assert reviewed.answer == guidance.fallback
    assert reviewed.passages == guidance.references
    assert reviewed.answer != answer
    assert len(reviewed.answer.split()) <= 160


def test_basic_care_never_bypasses_a_provider_content_block():
    question = "My baby has a nappy rash."
    guidance = get_care_guidance(question, 6)
    blocked = CoachingResult(PROVIDER_BLOCK_MESSAGE, [], blocked=True)
    reviewed, decision = review_coaching_result(blocked, guidance.references, 6, question)
    assert reviewed is blocked
    assert decision.blocked
    assert not decision.replaced_with_basic_care


def test_fallback_requires_the_exact_source_checked_references():
    question = "My baby has a nappy rash."
    guidance = get_care_guidance(question, 6)
    altered = replace(guidance.references[0], source_url="https://untrusted.example")
    result = CoachingResult("Give 5 mg of medicine.", [altered])
    _, decision = review_coaching_result(result, [altered], 6, question)
    assert decision.blocked
    assert not decision.replaced_with_basic_care


def test_requested_feeding_frequency_is_not_treated_as_an_unsolicited_schedule():
    question = "How many meals should my toddler have?"
    guidance = get_care_guidance(question, 18)
    assert guidance.allow_schedule
    result = CoachingResult("Offer three meals and two snacks.", guidance.references)
    reviewed, decision = review_coaching_result(result, guidance.references, 18, question)
    assert reviewed is result
    assert not decision.replaced_with_basic_care


def test_requested_sleep_duration_and_age_descriptions_are_not_unsolicited_timings():
    guidance = get_care_guidance("How much sleep does my toddler need?", 18)
    assert guidance.allow_timing
    assert "unrequested_sleep_timing" not in guidance.findings("Sleep needs vary; around 12 to 15 hours in total.")
    guidance = get_care_guidance("How can I help my three-week-old baby sleep?", 0.7)
    assert "unrequested_sleep_timing" not in guidance.findings(
        "For a three weeks old baby, use a calm routine and a flat cot, lying on their back.")


@pytest.mark.parametrize("question", [
    "What food can I make for myself while breastfeeding?",
    "I can't sleep while worrying about my baby.",
    "What food can I pretend to feed a doll?",
    "How do I sterilise a feeding bottle?",
    "My baby has an egg allergy. What foods can I offer?",
    "My baby refuses food. What should I do?",
])
def test_basic_care_selections_do_not_replace_other_types_of_care_requests(question):
    assert get_care_guidance(question, 6) is None


def test_basic_care_references_are_age_scoped_and_are_not_similarity_scores():
    young = get_care_guidance("What food can I offer my baby?", 3)
    older = get_care_guidance("What food can I offer my baby?", 18)
    assert "milk-feeding" in young.references[0].passage_id
    assert "toddler-foods" in older.references[0].passage_id
    assert all(p.selection_method == "source_checked_basic_care" and p.score == 0 for p in older.references)
    assert get_care_guidance("What food can I offer my child?", 25) is None


def test_feeding_statement_follow_up_keeps_the_same_age_scoped_care_selection():
    request = "I am feeding my baby."
    first = get_care_guidance(request, 6)
    context = [{"role": "user", "text": request},
               {"role": "assistant", "text": "Try soft foods if ready.", "caregiver_request": request}]
    follow_up = get_care_guidance("What else can I try?", 6, context)
    assert follow_up.references == first.references
    assert "first-foods" in get_care_guidance("What soft foods can I try with my baby?", 9).references[0].passage_id


def test_sleep_with_reflux_retains_the_reflux_specific_precautions():
    guidance = get_care_guidance("How should my baby sleep with reflux?", 3)
    assert guidance.topic == "reflux"
    result = CoachingResult("Let your baby sleep on their front on a flat mattress, not their back. Ask a doctor if worried.", guidance.references)
    reviewed, decision = review_coaching_result(result, guidance.references, 3, "How should my baby sleep with reflux?")
    assert decision.replaced_with_basic_care
    assert "unsafe_sleep_position_advice" in decision.reasons
    assert reviewed.answer == guidance.fallback
