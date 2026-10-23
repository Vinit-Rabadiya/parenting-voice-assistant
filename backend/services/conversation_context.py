"""Bounded conversation context, separate from retrieved reference evidence."""

import re


MAX_CONTEXT_MESSAGES = 6
MAX_CONTEXT_CHARACTERS = 3000


def is_follow_up(question: str) -> bool:
    normalized = " ".join(question.lower().split()).rstrip("?.!")
    return re.fullmatch(
        r"(?:what else(?: can i (?:try|do))?|(?:any )?more (?:ideas|suggestions|examples)|"
        r"(?:can|could) you (?:give|suggest) (?:me )?(?:another|more) (?:idea|ideas|activity|activities|example|examples)|"
        r"(?:can|could) you explain (?:that|this)|how (?:do|can) i do (?:that|this)|"
        r"(?:another|one more) (?:idea|activity|example)(?: please)?|something else|"
        r"tell me more|anything else(?: i can (?:try|do))?|please explain (?:that|this))",
        normalized,
    ) is not None


def select_conversation_context(messages: list[dict]) -> list[dict[str, str]]:
    """Keep complete recent answered pairs; stop at a safety/error boundary."""
    selected: list[dict[str, str]] = []
    characters = 0
    for index in range(len(messages) - 2, -1, -2):
        user, assistant = messages[index:index + 2]
        if (user.get("role") != "user" or assistant.get("role") != "assistant"
                or assistant.get("status") != "answered"
                or assistant.get("safety", "not_flagged") != "not_flagged"):
            break
        question, answer = user.get("text"), assistant.get("text")
        if not isinstance(question, str) or not isinstance(answer, str) or not question.strip() or not answer.strip():
            break
        pair_size = len(question) + len(answer)
        if characters + pair_size > MAX_CONTEXT_CHARACTERS or len(selected) + 2 > MAX_CONTEXT_MESSAGES:
            break
        selected[:0] = [{"role": "user", "text": question}, {"role": "assistant", "text": answer}]
        characters += pair_size
    return selected


def contextual_retrieval_query(question: str, context: list[dict[str, str]]) -> str:
    """Add a caregiver topic only for explicit follow-ups, never prior AI claims."""
    if is_follow_up(question):
        for message in reversed(context):
            if message["role"] == "user" and not is_follow_up(message["text"]):
                return f"{message['text'][:600]}\nFollow-up: {question}"
    return question
