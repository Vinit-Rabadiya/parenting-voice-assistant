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
    ("Try soft-boiled egg mixed with mashed avocado.", "undercooked_egg_suggestion"),
    ("Offer runny eggs for breakfast.", "undercooked_egg_suggestion"),
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
    "Avoid raw eggs. Cook eggs thoroughly before serving.",
    "Do not serve soft-boiled eggs.",
    "Offer fully cooked egg instead of runny eggs.",
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
    ("My baby has a blocked nose.", 6, "Offer frequent, smaller breast milk or formula feeds. Ask a doctor if worried.", "individual_feeding_change"),
    ("My baby has a blocked nose.", 6, "Use a few drops of sterile saline solution in each nostril. Ask a doctor if worried.", "individual_nasal_product_instruction"),
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


@pytest.mark.parametrize("question,age,topic", [
    ("My baby has watery poo.", 3, "stomach_upset"),
    ("My baby has loose watery stools.", 2, "stomach_upset"),
    ("My child has a cough and runny nose.", 12, "cough_cold"),
    ("How can I help sore gums?", 9, "teething"),
    ("What can soothe gums while teeth come through?", 9, "teething"),
    ("How can I soothe their gums?", 9, "teething"),
    ("My baby has gum discomfort.", 9, "teething"),
    ("My baby has hard poo.", 2, "stools"),
    ("My baby's eyes look yellow.", 0.3, "jaundice"),
    ("How should I brush my baby's teeth?", 12, "oral_care"),
    ("What do I bring to a clinic visit?", 18, "records"),
    ("My child is having tantrums.", 24, "behaviour"),
    ("How can we mark the second birthday?", 24, "birthday"),
])
def test_expanded_care_selects_traceable_facts_for_statements_and_questions(question, age, topic):
    guidance = get_care_guidance(question, age)
    assert guidance.topic == topic
    assert guidance.references and len(guidance.fallback.split()) <= 160
    assert all(p.source_url.startswith("https://") for p in guidance.references)


def test_multiple_symptoms_and_age_ineligible_packets_stay_with_general_pipeline():
    assert get_care_guidance("My baby has a cough and fever.", 9) is None
    assert get_care_guidance("My baby's eyes look yellow.", 9) is None
    guidance = get_care_guidance("My baby is teething.", 1)
    assert "young-gum-discomfort" in guidance.references[0].passage_id
    assert "teething ring" not in guidance.fallback


def test_all_permitted_care_fallbacks_pass_the_existing_output_checks():
    from backend.services.care_guidance import load_references
    for entry in load_references()["entries"]:
        answer = "\n\n".join(r["text"] for r in entry["references"])
        decision = inspect_response(answer, [], [], min(entry["min_months"], 24))
        assert not decision.blocked, (entry["id"], decision.reasons)


def test_spice_question_uses_traceable_food_guidance_without_an_invented_age_ban():
    question = "At what time should I feed a 23 month old some chillies?"
    guidance = get_care_guidance(question, 23)
    assert guidance.topic == "food_flavours"
    assert guidance.references[0].pdf_page == 54
    assert "gradually" in guidance.fallback
    result = CoachingResult("Avoid all spices because her immature digestive system cannot handle them.", guidance.references)
    reviewed, decision = review_coaching_result(result, guidance.references, 23, question)
    assert decision.replaced_with_basic_care
    assert reviewed.answer == guidance.fallback
    assert get_care_guidance("My baby has chilli in her eyes.", 23) is None
    assert get_care_guidance("Can I introduce spices?", 3) is None


@pytest.mark.parametrize("answer", ["Offer a tiny pinch once a day.", "Offer it mid-morning or early afternoon before bedtime."])
def test_spice_sources_do_not_establish_a_measured_quantity_or_feeding_schedule(answer):
    question = "When can my 23-month-old try chilli?"
    guidance = get_care_guidance(question, 23)
    reviewed, decision = review_coaching_result(CoachingResult(answer, guidance.references), guidance.references, 23, question)
    assert decision.replaced_with_basic_care
    assert "unsupported_food_flavour_schedule" in decision.reasons
    assert reviewed.answer == guidance.fallback


def test_teething_with_diarrhoea_preserves_the_illness_boundary():
    question = "Does teething explain loose stools?"
    guidance = get_care_guidance(question, 12)
    assert guidance.topic == "teething_illness"
    result = CoachingResult("Increased drool can affect digestion during teething. Ask a doctor if worried.", guidance.references)
    reviewed, decision = review_coaching_result(result, guidance.references, 12, question)
    assert decision.replaced_with_basic_care
    assert "unsupported_teething_explanation" in decision.reasons
    assert "no evidence that teething causes diarrhoea" in reviewed.answer


def test_solid_food_preferences_are_separate_from_young_infant_feeding_problems():
    question = "My baby refuses food. What should I do?"
    assert get_care_guidance(question, 3) is None
    guidance = get_care_guidance(question, 9)
    assert guidance.topic == "food_refusal"
    assert "already eating solids" in guidance.fallback
    assert "health professional" in guidance.fallback


@pytest.mark.parametrize("answer", [
    "Ask a pharmacist or clinician before using nose drops. Seek medical assessment if feeding is affected.",
    "A health professional should be consulted before using nose drops. Seek medical assessment if feeding is affected.",
    "Do not use nasal drops without professional advice. Seek medical assessment if feeding is affected.",
])
def test_cold_care_preserves_professional_first_product_advice(answer):
    guidance = get_care_guidance("My baby has a cold.", 9)
    assert "individual_nasal_product_instruction" not in guidance.findings(answer)


@pytest.mark.parametrize("question", [
    "My baby cries whenever I fasten the car-seat straps.",
    "My baby cries during clothing changes.",
])
def test_specific_crying_trigger_uses_retrieval_instead_of_generic_soothing_pack(question):
    assert get_care_guidance(question, 5) is None


def test_ordinary_crying_still_has_local_comfort_references():
    assert get_care_guidance("My baby is crying. How can I comfort her?", 5).topic == "soothing"


@pytest.mark.parametrize("question", [
    "Suggest two quiet games for my child while someone sleeps in our room.",
    "What books can we share after bedtime? I want book ideas, not a sleep routine.",
    "My baby cries when the singing ends. Can you suggest other songs and ways to play together?",
])
def test_background_sleep_and_crying_do_not_replace_a_requested_activity(question):
    assert get_care_guidance(question, 16) is None


@pytest.mark.parametrize("question", [
    "My child has no fever, but keeps rubbing her ear. What should I watch for?",
    "My child is not vomiting. What should I pack for a nursery visit?",
    "My baby has no signs of jaundice. How can I play with her on the floor?",
])
def test_denied_symptoms_do_not_select_an_unrelated_illness_pack(question):
    assert get_care_guidance(question, 8) is None


def test_denial_of_one_symptom_does_not_hide_a_different_present_concern():
    guidance = get_care_guidance("My child has no fever but is vomiting. What should I watch for?", 8)
    assert guidance.topic == "stomach_upset"


@pytest.mark.parametrize("question", [
    "My baby does not have a fever. What book can we share?",
    "My daughter does not have a cold. How can we play together?",
    "My daughter doesn't have a fever. Suggest a quiet game.",
    "My child has no cough or fever. How can I encourage pointing?",
    "My child has no fever, cough or vomiting. How can I encourage pointing?",
    "My baby isn't showing any signs of jaundice. What book can we share?",
])
def test_negative_predicates_and_coordinated_denials_do_not_establish_a_health_topic(question):
    assert get_care_guidance(question, 2) is None


@pytest.mark.parametrize("question,topic", [
    ("My child does not have a fever but is vomiting. What should I watch for?", "stomach_upset"),
    ("My child has no cough or fever but is vomiting. What should I watch for?", "stomach_upset"),
    ("My child has no appetite and is vomiting. What should I watch for?", "stomach_upset"),
    ("My child is not just vomiting; she has a fever too. What should I watch for?", None),
    ("My child is not sleeping. How can I help her settle?", "sleep"),
    ("My child is not eating. What foods can I offer?", "feeding"),
])
def test_negation_does_not_hide_a_positive_report_or_an_activity_difficulty(question, topic):
    guidance = get_care_guidance(question, 8)
    assert (guidance.topic if guidance else None) == topic


@pytest.mark.parametrize("question,age,topic,answer,reason", [
    ("Can I pack my baby's cut fruit the night before without a refrigerator?", 11, "food_storage",
     "Yes, put the cut fruit in an airtight container in your bag overnight.", "missing_food_cooling_precaution"),
    ("Can I pack my baby's cut fruit the night before without a refrigerator?", 11, "food_storage",
     "Refrigerate at first, then leave the sealed container in your bag overnight.", "missing_overnight_storage_boundary"),
    ("My eight-month-old is learning to drink from an open cup.", 8, "cup_drinking",
     "Practise scooping bath water and pouring it between cups in the tub.", "unrelated_bath_activity"),
    ("My ten-week-old has cradle cap. What changes need a clinic visit?", 2.3, "cradle_cap",
     "Massage olive oil into the scales. Consult a doctor for swelling.", "individual_scalp_product_selection"),
])
def test_fresh_audit_failures_use_relevant_checked_fallback(question, age, topic, answer, reason):
    guidance = get_care_guidance(question, age)
    assert guidance.topic == topic
    reviewed, decision = review_coaching_result(CoachingResult(answer, guidance.references), guidance.references, age, question)
    assert reason in decision.reasons
    assert decision.replaced_with_basic_care
    assert reviewed.answer == guidance.fallback
    assert reviewed.passages == guidance.references


def test_storage_constraints_survive_an_indirect_follow_up():
    request = "For my eleven-month-old, suggest two portable snack ideas. We have no refrigerator."
    context = [{"role": "user", "text": request},
               {"role": "assistant", "text": "Soft fruit.", "caregiver_request": request}]
    guidance = get_care_guidance("Can I pack it the night before and keep it in my bag?", 11, context)
    assert guidance.topic == "food_storage"
    assert not guidance.findings(guidance.fallback)
    assert "ordinary bag" in guidance.fallback


def test_drinking_cup_support_does_not_offer_water_to_a_young_infant():
    assert get_care_guidance("Can my baby drink from an open cup?", 2) is None


@pytest.mark.parametrize("answer", [
    "Offer a smooth stone and a paper bag for texture play.",
    "Fill a zip-lock bag with water and let your child squeeze it.",
])
def test_unsuitable_play_materials_are_withheld_before_delivery(answer):
    _, decision = review_coaching_result(CoachingResult(answer, []), [], 17, "Suggest screen-free texture play.")
    assert decision.blocked and "unsuitable_child_play_material" in decision.reasons


def test_bag_warning_or_hygiene_use_is_not_an_unsafe_play_suggestion():
    for question, answer in [
        ("Suggest texture play.", "Avoid offering stones or paper bags. Use a soft cloth."),
        ("Suggest texture play.", "Use a soft cloth instead of plastic bags."),
        ("Suggest texture play.", "Provide a sensory toy without loose stones."),
        ("How do I dispose of dirty nappies?", "Use a plastic bag to contain waste, kept away from children."),
    ]:
        _, decision = review_coaching_result(CoachingResult(answer, []), [], 17, question)
        assert not decision.blocked


def test_cot_settling_does_not_allow_heating_or_invented_sleep_timings():
    question = "My eight-week-old wakes when I transfer him into the cot."
    guidance = get_care_guidance(question, 2)
    assert guidance.topic == "sleep"
    assert "sleep_surface_heating_instruction" in guidance.findings("Warm the cot with a heating pad; sleep flat on the back.")


@pytest.mark.parametrize("answer", [
    "Let her play with toys in a shallow basin of water beside you.",
    "Provide paper to tear into small pieces and glue into a collage.",
])
def test_busy_caregiver_activity_requires_appropriate_materials_and_supervision(answer):
    question = "How can I keep her busy while I fold towels?"
    guidance = get_care_guidance(question, 19)
    reviewed, decision = review_coaching_result(CoachingResult(answer, guidance.references), guidance.references, 19, question)
    assert decision.replaced_with_basic_care
    assert "activity_exceeds_available_supervision" in decision.reasons
    assert reviewed.answer == guidance.fallback



def test_one_handed_follow_up_does_not_transfer_the_constraint_to_the_child():
    original = "I need two ways to keep her busy while I fold towels."
    context = [{"role": "user", "text": original},
               {"role": "assistant", "text": "Sort large toys and look at a book.", "caregiver_request": original}]
    question = "Could you keep the first idea and make the other easier to do one-handed?"
    guidance = get_care_guidance(question, 19, context)
    assert guidance.caregiver_one_handed
    assert "child's hands" in guidance.instructions
    reviewed, decision = review_coaching_result(
        CoachingResult("Let her use a book while you fold with both hands.", guidance.references),
        guidance.references, 19, question, context)
    assert decision.replaced_with_basic_care
    assert "conflicting_caregiver_hand_constraint" in decision.reasons
    assert reviewed.answer == guidance.fallback
