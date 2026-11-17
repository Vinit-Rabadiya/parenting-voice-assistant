import pytest

from backend.services.conversation_context import (
    MAX_CONTEXT_CHARACTERS, MAX_CONTEXT_MESSAGES, contextual_retrieval_query,
    contextual_age_months, is_follow_up, needs_topic_clarification, select_conversation_context,
    caregiver_request,
    semantic_retrieval_query,
)


def pair(question="How can I talk during feeding?", answer="Talk softly.", status="answered"):
    return [{"role": "user", "text": question},
            {"role": "assistant", "text": answer, "status": status}]


@pytest.mark.parametrize("question", ["What else can I try?", "More ideas", "Can you explain that?", "Another activity please.", "Tell me more", "Anything else I can do?", "Please explain that."])
def test_recognizes_explicit_follow_ups(question):
    assert is_follow_up(question)


@pytest.mark.parametrize("question", [
    "That didn't help.", "It is not working", "Is that safe?", "How often?",
    "For how long?", "She still won\u2019t take it.",
    "How many times a day?", "What about at night?", "Is that suitable for her?",
    "She refuses it.", "Yes please.",
])
def test_short_follow_ups_keep_the_latest_caregiver_topic(question):
    context = select_conversation_context(pair("I am feeding my baby.", "Talk gently."))
    assert contextual_retrieval_query(question, context) == f"I am feeding my baby.\nFollow-up: {question}"


def test_short_follow_up_uses_new_topic_instead_of_an_older_activity():
    context = select_conversation_context(pair() + pair("I am bathing my baby.", "Keep supporting the head."))
    assert contextual_retrieval_query("Is that safe?", context).startswith("I am bathing my baby.")
    assert contextual_retrieval_query("That didn't help.", []) == "That didn't help."


@pytest.mark.parametrize("question", ["I am feeding my baby", "How do I fix a car?", "My baby cannot breathe", "What is the weather?",
                                      "What if my child refuses a toothbrush?", "What if a baby has trouble swallowing?"])
def test_new_topics_and_danger_reports_are_not_generic_follow_ups(question):
    assert not is_follow_up(question)


def test_keeps_recent_complete_pairs_in_chronological_order():
    messages = sum((pair(f"Question {index}") for index in range(5)), [])
    selected = select_conversation_context(messages)
    assert len(selected) == MAX_CONTEXT_MESSAGES
    assert selected[0]["text"] == "Question 1"
    assert all(message["text"] != "Question 0" for message in selected)
    assert selected[-2]["text"] == "Question 4"


def test_limits_text_without_cutting_a_message_in_half():
    selected = select_conversation_context(pair("A" * 1000, "B" * (MAX_CONTEXT_CHARACTERS - 999)))
    assert selected == []
    selected = select_conversation_context(pair("A" * 1000, "B" * 1000) + pair("C" * 1000, "D" * 1000))
    assert len(selected) == 4
    assert sum(len(message["text"]) for message in selected) <= MAX_CONTEXT_CHARACTERS
    older = pair("An older request", "An older answer")
    assert select_conversation_context(older + pair("A" * 1000, "B" * 1000) + pair("C" * 1000, "D" * 1000)) == selected


@pytest.mark.parametrize("status", ["no_evidence", "safety_blocked", "escalated", "crisis_support", "caregiver_support"])
def test_does_not_reuse_context_before_a_safety_or_unsuccessful_answer(status):
    assert select_conversation_context(pair() + pair(status=status)) == []


def test_clarification_context_is_available_but_cannot_bridge_a_safety_boundary():
    clarification = pair("She still won't take it.", "What are you offering?", status="no_evidence")
    clarification[-1]["response_kind"] = "clarification"
    context = select_conversation_context(pair(status="escalated") + clarification)
    assert context == [{"role": "user", "text": "She still won't take it."},
                       {"role": "assistant", "text": "What are you offering?", "response_kind": "clarification"}]
    clarification[-1]["safety"] = "escalate"
    assert select_conversation_context(clarification) == []


def test_unresolved_clarification_does_not_become_a_reference_search_topic():
    clarification = pair("I am batting my baby.", "Do you mean bathing or something else?", status="no_evidence")
    clarification[-1]["response_kind"] = "clarification"
    context = select_conversation_context(pair("I am feeding my baby.") + clarification)
    assert contextual_retrieval_query("Is that safe?", context) == "Is that safe?"
    assert contextual_retrieval_query("Bathing my baby.", context) == "Bathing my baby."


def test_drops_non_context_fields_and_rejects_malformed_pairs():
    messages = pair()
    messages[0]["account_id"] = "private-account"
    assert "account_id" not in select_conversation_context(messages)[0]
    assert select_conversation_context([{"role": "assistant", "text": "Incomplete"}]) == []


def test_follow_up_search_uses_caregiver_topic_not_previous_model_claims():
    context = select_conversation_context(pair(answer="UNVERIFIED_PREVIOUS_CLAIM"))
    query = contextual_retrieval_query("What else can I try?", context)
    assert "How can I talk during feeding?" in query
    assert "What else can I try?" in query
    assert "UNVERIFIED_PREVIOUS_CLAIM" not in query


def test_new_topic_is_not_expanded_and_follow_ups_can_find_an_earlier_topic():
    context = select_conversation_context(pair() + pair("What else can I try?"))
    assert contextual_retrieval_query("What is the weather?", context) == "What is the weather?"
    assert "How can I talk during feeding?" in contextual_retrieval_query("More ideas", context)


def test_follow_up_without_an_anchor_remains_unchanged():
    assert contextual_retrieval_query("What else can I try?", []) == "What else can I try?"


@pytest.mark.parametrize("reply", ["sorry I meant she is 23 months", "23 months", "Actually, she is 23 months old"])
def test_age_correction_resumes_the_question_after_an_age_scope_refusal(reply):
    topic = "At what time should I feed a 3 year old some chillies?"
    refused = pair(topic, "This service covers birth through 24 months.", status="no_evidence")
    refused[-1].update(response_kind="age_out_of_scope", subject_age_override=36)
    context = select_conversation_context(pair("How often should I change a diaper?") + refused)
    assert len(context) == 2
    assert caregiver_request(reply, context) == topic
    assert contextual_age_months(reply, context) == 23
    assert contextual_retrieval_query(reply, context) == f"{topic}\nFollow-up: {reply}"


@pytest.mark.parametrize("complaint", ["you did not respond to the question", "You didn't answer my question.", "That is not what I asked", "You misunderstood me"])
def test_repair_request_keeps_the_food_question_and_corrected_age(complaint):
    topic = "At what time should I feed a 3 year old some chillies?"
    messages = pair(topic, "This service covers birth through 24 months.", status="no_evidence")
    messages[-1].update(response_kind="age_out_of_scope", subject_age_override=36)
    messages += pair("sorry I meant she is 23 months", "Unrelated play advice.")
    # Older stored turns may have incorrectly kept the short reply as their topic.
    messages[-1].update(caregiver_request="sorry I meant she is 23 months", subject_age_override=23)
    context = select_conversation_context(messages)
    assert is_follow_up(complaint)
    assert caregiver_request(complaint, context) == topic
    assert contextual_age_months(complaint, context) == 23
    assert "Unrelated play advice" not in contextual_retrieval_query(complaint, context)
    assert caregiver_request("I am bathing my baby.", context) == "I am bathing my baby."


@pytest.mark.parametrize("question", [
    "what is full bath, top and tailing?", "What does top and tailing mean?",
    "Can you explain a full bath?", "What is top-and-tailing?",
])
def test_named_clarification_keeps_caregiver_topic_without_copying_assistant_claims(question):
    context = select_conversation_context(pair(
        "I am bathing my baby.",
        "Are you doing a full bath or top and tailing? UNVERIFIED_CLAIM",
    ))
    query = contextual_retrieval_query(question, context)
    assert query == f"I am bathing my baby.\nFollow-up: {question}"
    assert "UNVERIFIED_CLAIM" not in query


def test_new_named_topic_and_missing_context_are_not_borrowed_clarifications():
    context = select_conversation_context(pair("I am bathing my baby.", "Use a full bath or top and tailing."))
    assert contextual_retrieval_query("What is a vaccine?", context) == "What is a vaccine?"
    assert contextual_retrieval_query("What does top and tailing mean?", []) == "What does top and tailing mean?"


def test_new_explicit_subject_does_not_inherit_an_older_child_age():
    context = select_conversation_context(pair("My 6-week-old baby feeds often."))
    question = "My 12-month-old child is eating breakfast."
    assert contextual_retrieval_query(question, context) == question


def test_bare_age_reply_is_used_only_after_a_clarification():
    messages = pair("Food ideas for my toddler?", "How old is the child you mean?", status="no_evidence")
    messages[-1]["response_kind"] = "clarification"
    context = select_conversation_context(messages)
    assert contextual_age_months("18 months", context) == 18
    assert contextual_age_months("18 months", []) is None
    assert contextual_age_months("Three times a day", context) is None
    assert contextual_age_months("My baby is 6 weeks old", context) == pytest.approx(42 / 30.4375)


@pytest.mark.parametrize("reply", ["eighteen months", "She is eighteen months old", "one year old"])
def test_word_age_reply_resumes_the_pending_request(reply):
    messages = pair("Food ideas for my toddler?", "How old is the child you mean?", status="no_evidence")
    messages[-1].update(response_kind="clarification", clarification_field="age")
    context = select_conversation_context(messages)
    assert caregiver_request(reply, context) == "Food ideas for my toddler?"
    assert contextual_age_months(reply, context) == (12 if reply == "one year old" else 18)


@pytest.mark.parametrize("reply", ["Why?", "What about the second suggestion?", "What about the next three months?",
                                  "Also include optional vaccines.", "Please include optional vaccines.",
                                  "Could I do this after a feed?"])
def test_follow_up_variations_preserve_the_caregiver_request(reply):
    context = select_conversation_context(pair("Vaccines for my one-month-old baby for the next six months?", "Schedule information."))
    assert caregiver_request(reply, context) == context[0]["text"]
    assert contextual_age_months(reply, context) == 1


def test_demonstrative_before_a_new_topic_is_not_mistaken_for_a_generic_follow_up():
    assert not is_follow_up("Can I use this picture book with my baby?")


@pytest.mark.parametrize("reply", ["Actually one month", "Sorry, I meant one month old", "Actually she is one month old"])
def test_explicit_age_correction_resumes_an_answered_request_without_an_age_question(reply):
    context = select_conversation_context(pair("Vaccines for my six-month-old baby for the next six months?"))
    assert caregiver_request(reply, context) == context[0]["text"]
    assert contextual_age_months(reply, context) == 1
    assert contextual_age_months("one month", context) is None


def test_resolved_age_survives_bounded_history_without_trusting_generated_age_claims():
    messages = pair("What else can I try?", "Your baby is 36 months old. UNVERIFIED_CLAIM")
    messages[-1]["subject_age_override"] = 18
    context = select_conversation_context(messages)
    assert contextual_age_months("She refuses it.", context) == 18
    assert contextual_age_months("I am bathing my baby.", context) is None
    assert "UNVERIFIED_CLAIM" not in contextual_retrieval_query("She refuses it.", context)


@pytest.mark.parametrize("invalid", [True, "18", -1, float("nan"), float("inf")])
def test_invalid_stored_age_is_not_added_to_context(invalid):
    messages = pair()
    messages[-1]["subject_age_override"] = invalid
    assert "subject_age_months" not in select_conversation_context(messages)[-1]


def test_missing_referents_are_distinct_from_new_child_reports_and_continuing_turns():
    assert needs_topic_clarification("She refuses it.", [])
    assert needs_topic_clarification("What else can I try?", [])
    assert not needs_topic_clarification("She feels feverish.", [])
    context = select_conversation_context(pair("What else can I try?", "Try a different soft texture."))
    assert not needs_topic_clarification("What else can I try?", context)


def test_profile_age_snapshots_do_not_override_the_current_profile_age():
    messages = pair()
    messages[-1]["child_age_months"] = 6
    context = select_conversation_context(messages)
    assert contextual_age_months("What else can I try?", context) is None


@pytest.mark.parametrize("question,age_reply", [
    ("What food can I make for my toddler?", "18 months"),
    ("How can I settle my newborn at night?", "She is 2 weeks old"),
])
def test_age_reply_resumes_the_pending_request_for_search_and_later_follow_ups(question, age_reply):
    messages = pair(question, "How old is the child you mean?", status="no_evidence")
    messages[-1].update(response_kind="clarification", clarification_field="age")
    context = select_conversation_context(messages)
    assert caregiver_request(age_reply, context) == question
    assert contextual_retrieval_query(age_reply, context) == f"{question}\nFollow-up: {age_reply}"
    later = pair(age_reply, "An answer", status="answered")
    later[-1]["caregiver_request"] = question
    context = select_conversation_context(later)
    assert caregiver_request("What else can I try?", context) == question
    assert caregiver_request("I am bathing my baby.", context) == "I am bathing my baby."


def test_age_reply_does_not_resolve_an_ambiguous_action_clarification():
    messages = pair("I am batting my baby.", "Do you mean bathing or something else?", status="no_evidence")
    messages[-1]["response_kind"] = "clarification"
    context = select_conversation_context(messages)
    assert caregiver_request("18 months", context) == "18 months"


def test_carried_request_stays_within_the_existing_context_budget():
    messages = pair("A" * 1000, "B" * 1000) + pair("What else can I try?", "C" * 1000)
    messages[-1]["caregiver_request"] = "D" * 1200
    context = select_conversation_context(messages)
    assert len(context) == 2
    assert context[-1]["caregiver_request"] == "D" * 1200
    assert sum(len(m["text"]) + len(m.get("caregiver_request", "")) for m in context) <= MAX_CONTEXT_CHARACTERS


def test_generic_follow_up_after_named_clarification_keeps_original_topic():
    context = select_conversation_context(
        pair("I am bathing my baby.", "A full bath or top and tailing are different.")
        + pair("What does top and tailing mean?", "Wash selected areas outside the bath.")
    )
    assert contextual_retrieval_query("Tell me more", context).startswith("I am bathing my baby.")


def test_sourced_vaccine_education_allows_follow_up_but_unsourced_notices_do_not():
    messages = pair("What is TCV?", "TCV protects against typhoid.", status="vaccination_notice")
    assert select_conversation_context(messages) == []
    messages[-1]["citations"] = [{"source_url": "https://www.health.go.ke/"}]
    context = select_conversation_context(messages)
    assert len(context) == 2
    for question in ["What does that mean?", "What side effects can it have?"]:
        assert contextual_retrieval_query(question, context) == f"What is TCV?\nFollow-up: {question}"
    messages[-1]["safety"] = "escalate"
    assert select_conversation_context(messages) == []


@pytest.mark.parametrize("follow_up", [
    "The second choice needs cooking. Could you swap only that one for something I can pack as it is?",
    "Can I pack it the night before and keep it in my bag?",
    "Please keep the same age in mind and shorten it to a three-point checklist for my partner.",
    "Could you rewrite that for someone who reads only short sentences?",
])
def test_referential_edits_and_practical_follow_ups_keep_request_and_age(follow_up):
    original = "For my eleven-month-old, suggest two portable snack ideas with no refrigerator."
    messages = pair(original, "Try soft fruit.")
    messages[-1]["subject_age_override"] = 11
    context = select_conversation_context(messages)
    assert caregiver_request(follow_up, context) == original
    assert contextual_age_months(follow_up, context) == 11
    assert original in contextual_retrieval_query(follow_up, context)


def test_explicit_topic_change_replaces_context_age_and_request():
    context = select_conversation_context(pair("My child is twenty-one months. Suggest a sock sorting game."))
    question = "Now a different question: my eight-week-old wakes when I transfer him into the cot. Give two settling ideas."
    assert caregiver_request(question, context) == question
    assert contextual_age_months(question, context) == pytest.approx(56 / 30.4375)


@pytest.mark.parametrize("reply", [
    "Could you adapt the advice for a child who cannot walk yet?",
    "What if the crying begins before we arrive?",
    "Please change the plan so her grandmother can follow it.",
    "Instead of that, give me two things her grandfather can do while I finish eating.",
    "No, I meant seventeen months, not seven months.",
    "Actually she's seventeen months.",
])
def test_context_references_keep_the_request_across_different_sentence_forms(reply):
    original = "My daughter is fourteen months. How can I support her when I leave her with her grandmother?"
    messages = pair(original, "Use a short goodbye and a familiar routine.")
    messages[-1]["subject_age_override"] = 14
    context = select_conversation_context(messages)
    assert caregiver_request(reply, context) == original
    assert contextual_age_months(reply, context) == (17 if reply.startswith(("No,", "Actually")) else 14)


@pytest.mark.parametrize("reply", [
    "She has a red patch around her neck now. What should I watch for?",
    "She feels feverish.",
    "He wakes with a blocked nose. How can I keep him comfortable?",
    "Her neck gets red after wearing this bib. What should I watch for?",
])
def test_new_child_report_keeps_subject_age_without_reusing_previous_activity(reply):
    messages = pair("My baby is ten months. How can I help during a long bus journey?")
    messages[-1]["subject_age_override"] = 10
    context = select_conversation_context(messages)
    assert caregiver_request(reply, context) == reply
    assert contextual_retrieval_query(reply, context) == reply
    assert contextual_age_months(reply, context) == 10
    assert not needs_topic_clarification(reply, context)


def test_explicit_new_topic_overrides_incidental_references_to_old_advice():
    context = select_conversation_context(pair("Suggest a quiet game for my baby."))
    question = "A different question, unrelated to your advice: how do I wash reusable nappies?"
    assert caregiver_request(question, context) == question


def test_same_child_age_from_older_history_does_not_carry_the_old_topic_or_assistant_claim():
    context = select_conversation_context(pair(
        "Our little boy has just turned two months. Suggest a gentle way to share a story.",
        "Your child is ten months. Try a cloth book.",
    ))
    question = "He feels feverish."
    assert caregiver_request(question, context) == question
    assert contextual_age_months(question, context) == 2


def test_semantic_search_prioritizes_current_message_and_keeps_intermediate_constraints():
    original = "Suggest a simple sorting activity for my nineteen-month-old."
    refinement = "Keep the same activity, but without paper or loose small objects."
    messages = pair(original, "UNVERIFIED_SUGGESTION") + pair(refinement, "UNVERIFIED_REPLACEMENT")
    context = select_conversation_context(messages)
    current = "Could you adapt that for the bus journey tomorrow?"
    query = semantic_retrieval_query(current, context)
    assert query.startswith(current + "\n")
    assert original in query and refinement in query
    assert "UNVERIFIED" not in query


def test_semantic_search_uses_new_topic_without_borrowing_old_constraints():
    context = select_conversation_context(pair("My child dislikes having her hair washed."))
    current = "What should I put in the bag before a nursery visit?"
    assert semantic_retrieval_query(current, context) == current


def test_long_search_context_keeps_the_current_request_before_a_bounded_anchor():
    original = "My son is sixteen months. " + "Our previous routine was quite different. " * 24 + "Suggest a quiet activity."
    context = select_conversation_context(pair(original, "A previous answer."))
    current = "Instead of that, suggest something we can do without buying anything."
    query = semantic_retrieval_query(current, context)
    assert query.startswith(current)
    assert "My son is sixteen months." in query
    assert "Suggest a quiet activity." in query
    assert len(query) < len(current) + 450


def test_semantic_search_retains_refinements_when_original_turn_leaves_the_window():
    original = "Suggest a large-object sorting activity for my twenty-month-old."
    refinements = [
        "Keep the same activity but without paper or small parts.",
        "Please shorten that for the grandmother.",
        "What about the second option?",
        "Make that suitable for a short bus journey.",
    ]
    messages = pair(original)
    for text in refinements:
        turn = pair(text)
        turn[-1]["caregiver_request"] = original
        messages += turn
    context = select_conversation_context(messages)
    assert len(context) == MAX_CONTEXT_MESSAGES
    assert all(message["text"] != original for message in context)
    query = semantic_retrieval_query("Can you simplify that?", context)
    assert original in query
    assert all(refinement in query for refinement in refinements)
    assert sum(len(m["text"]) + len(m.get("caregiver_request", "")) for m in context) <= MAX_CONTEXT_CHARACTERS


def test_carried_refinements_do_not_cross_a_topic_change_within_the_window():
    first = "Suggest a sorting activity for my twenty-month-old."
    old_refinement = "Keep the same activity but without paper or small parts."
    second = "How can I make hair washing calmer?"
    new_refinement = "Could you adapt that so her father can do it?"
    old_turn = pair(old_refinement)
    old_turn[-1]["caregiver_request"] = first
    new_turn = pair(new_refinement)
    new_turn[-1]["caregiver_request"] = second
    context = select_conversation_context(pair(first) + old_turn + pair(second) + new_turn)
    query = semantic_retrieval_query("Can you simplify that?", context)
    assert second in query and new_refinement in query
    assert first not in query and old_refinement not in query
