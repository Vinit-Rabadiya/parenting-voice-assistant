"""Bounded conversation context, separate from retrieved reference evidence."""

import re


MAX_CONTEXT_MESSAGES = 6
MAX_CONTEXT_CHARACTERS = 3000


def is_follow_up(question: str) -> bool:
    normalized = " ".join(question.lower().replace("\u2019", "'").split()).rstrip("?.!")
    return re.fullmatch(
        r"(?:what else(?: can i (?:try|do))?|(?:any )?more (?:ideas|suggestions|examples)|"
        r"(?:can|could) you (?:give|suggest) (?:me )?(?:another|more) (?:idea|ideas|activity|activities|example|examples)|"
        r"(?:can|could) you explain (?:that|this)|how (?:do|can) i do (?:that|this)|"
        r"(?:another|one more) (?:idea|activity|example)(?: please)?|something else|"
        r"tell me more|anything else(?: i can (?:try|do))?|please explain (?:that|this)|"
        r"(?:is|was) (?:that|this|it) safe|how (?:often|long|much)|for how long|"
        r"(?:that|this|it) (?:did not|didn't|does not|doesn't) (?:help|work)|"
        r"(?:that|this|it) (?:is not|isn't|still isn't) (?:helping|working)|"
        r"(?:he|she|they|my baby) still (?:won't|will not|doesn't|does not) "
        r"(?:take|like|want|try) (?:it|that|this))",
        normalized,
    ) is not None


def select_conversation_context(messages: list[dict]) -> list[dict[str, str]]:
    """Keep bounded answered/clarification pairs; stop at a safety/error boundary."""
    selected: list[dict[str, str]] = []
    characters = 0
    for index in range(len(messages) - 2, -1, -2):
        user, assistant = messages[index:index + 2]
        usable = (assistant.get("status") == "answered" or (
            assistant.get("status") == "no_evidence"
            and assistant.get("response_kind") == "clarification"
        ))
        if (user.get("role") != "user" or assistant.get("role") != "assistant"
                or not usable
                or assistant.get("safety", "not_flagged") != "not_flagged"):
            break
        question, answer = user.get("text"), assistant.get("text")
        if not isinstance(question, str) or not isinstance(answer, str) or not question.strip() or not answer.strip():
            break
        pair_size = len(question) + len(answer)
        if characters + pair_size > MAX_CONTEXT_CHARACTERS or len(selected) + 2 > MAX_CONTEXT_MESSAGES:
            break
        previous_answer = {"role": "assistant", "text": answer}
        if assistant.get("response_kind") == "clarification":
            previous_answer["response_kind"] = "clarification"
        selected[:0] = [{"role": "user", "text": question}, previous_answer]
        characters += pair_size
    return selected


def contextual_retrieval_query(question: str, context: list[dict[str, str]]) -> str:
    """Add a caregiver topic only for explicit follow-ups, never prior AI claims."""
    # A request for clarification is not a resolved activity or factual answer.
    # Keep it available to generation, but do not use its ambiguous input as a
    # retrieval anchor or jump back to an older topic across that clarification.
    if context and context[-1].get("response_kind") == "clarification":
        return question
    clarification = clarifies_recent_answer(question, context)
    if is_follow_up(question) or clarification:
        for index in range(len(context) - 1, -1, -1):
            message = context[index]
            if (message["role"] == "user" and not is_follow_up(message["text"])
                    and not clarifies_recent_answer(message["text"], context[:index])):
                return f"{message['text'][:600]}\nFollow-up: {question}"
    return question


def clarifies_recent_answer(question: str, context: list[dict[str, str]]) -> bool:
    """Recognise a quoted term as context, not as verified reference evidence."""
    normalized = " ".join(re.findall(r"\w+", question.lower().replace(",", " or ")))
    match = re.fullmatch(
        r"(?:what (?:is|are)|what is meant by|(?:can|could) you explain|explain) (.+?)"
        r"|what (?:does|do) (.+?) mean", normalized,
    )
    if match is None or not context or context[-1].get("role") != "assistant":
        return False
    terms = [re.sub(r"^(?:a|an|the) ", "", term.strip())
             for term in re.split(r"\b(?:or|versus)\b", match.group(1) or match.group(2))]
    answer = " " + " ".join(re.findall(r"\w+", context[-1]["text"].lower())) + " "
    # Require meaningful terms from the latest permitted answer. New topics
    # remain standalone; no previous assistant sentence is copied into search.
    return all(len(term.strip()) >= 4 and f" {term.strip()} " in answer for term in terms)
