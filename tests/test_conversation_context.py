import pytest

from backend.services.conversation_context import (
    MAX_CONTEXT_CHARACTERS, MAX_CONTEXT_MESSAGES, contextual_retrieval_query,
    is_follow_up, select_conversation_context,
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
])
def test_short_follow_ups_keep_the_latest_caregiver_topic(question):
    context = select_conversation_context(pair("I am feeding my baby.", "Talk gently."))
    assert contextual_retrieval_query(question, context) == f"I am feeding my baby.\nFollow-up: {question}"


def test_short_follow_up_uses_new_topic_instead_of_an_older_activity():
    context = select_conversation_context(pair() + pair("I am bathing my baby.", "Keep supporting the head."))
    assert contextual_retrieval_query("Is that safe?", context).startswith("I am bathing my baby.")
    assert contextual_retrieval_query("That didn't help.", []) == "That didn't help."


@pytest.mark.parametrize("question", ["I am feeding my baby", "How do I fix a car?", "My baby cannot breathe", "What is the weather?"])
def test_new_topics_and_danger_reports_are_not_generic_follow_ups(question):
    assert not is_follow_up(question)


def test_keeps_recent_complete_pairs_in_chronological_order():
    messages = sum((pair(f"Question {index}") for index in range(5)), [])
    selected = select_conversation_context(messages)
    assert len(selected) == MAX_CONTEXT_MESSAGES
    assert selected[0]["text"] == "Question 2"
    assert selected[-2]["text"] == "Question 4"


def test_limits_text_without_cutting_a_message_in_half():
    selected = select_conversation_context(pair("A" * 1600, "B" * 1500))
    assert selected == []
    selected = select_conversation_context(pair("A" * 1000, "B" * 1000) + pair("C" * 1000, "D" * 1000))
    assert len(selected) == 2
    assert sum(len(message["text"]) for message in selected) <= MAX_CONTEXT_CHARACTERS


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


def test_generic_follow_up_after_named_clarification_keeps_original_topic():
    context = select_conversation_context(
        pair("I am bathing my baby.", "A full bath or top and tailing are different.")
        + pair("What does top and tailing mean?", "Wash selected areas outside the bath.")
    )
    assert contextual_retrieval_query("Tell me more", context).startswith("I am bathing my baby.")
