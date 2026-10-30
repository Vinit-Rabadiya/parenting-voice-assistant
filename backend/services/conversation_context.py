"""Bounded conversation context, separate from retrieved reference evidence."""

import re
from math import isfinite

from backend.services.age import message_age_months
from backend.services.care_response import AGE_CLARIFICATION_MESSAGES

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
        r"what (?:does|do) (?:that|this|it|they) mean|"
        r"what side[ -]?effects? can (?:it|they|that|this) (?:have|cause)|"
        r"what are (?:its|their) side[ -]?effects?|"
        r"(?:is|was) (?:that|this|it) safe|how (?:often|long|much)|for how long|"
        r"how many times(?: (?:a|per|each) (?:day|night|week))?|"
        r"what about (?:at night|during the day|bedtime|that|this|it|them|those)|"
        r"(?:yes|no)(?: please| thank you| thanks)?|"
        r"(?:is|are|was|were|can|could|should|will|would|does|do) "
        r"(?:that|this|it|they|those|these)\b.{0,100}|"
        r"(?:he|she|they)\b.{1,160}|"
        r"(?:that|this|it) (?:did not|didn't|does not|doesn't) (?:help|work)|"
        r"(?:that|this|it) (?:is not|isn't|still isn't) (?:helping|working)|"
        r"(?:he|she|they|my baby) still (?:won't|will not|doesn't|does not) "
        r"(?:take|like|want|try) (?:it|that|this))",
        normalized,
    ) is not None


def select_conversation_context(messages: list[dict]) -> list[dict]:
    """Keep bounded answers/clarifications; stop at a safety/error boundary."""
    selected: list[dict] = []
    characters = 0
    for index in range(len(messages) - 2, -1, -2):
        user, assistant = messages[index:index + 2]
        usable = (assistant.get("status") == "answered" or (
            assistant.get("status") == "no_evidence"
            and assistant.get("response_kind") == "clarification"
        ) or (
            assistant.get("status") == "vaccination_notice"
            and bool(assistant.get("citations"))
        ))
        if (user.get("role") != "user" or assistant.get("role") != "assistant"
                or not usable
                or assistant.get("safety", "not_flagged") != "not_flagged"):
            break
        question, answer = user.get("text"), assistant.get("text")
        if not isinstance(question, str) or not isinstance(answer, str) or not question.strip() or not answer.strip():
            break
        request = assistant.get("caregiver_request")
        keep_request = (not selected and isinstance(request, str)
                        and 2 <= len(request.strip()) <= 1200 and request.strip() != question.strip())
        pair_size = len(question) + len(answer) + (len(request.strip()) if keep_request else 0)
        if characters + pair_size > MAX_CONTEXT_CHARACTERS or len(selected) + 2 > MAX_CONTEXT_MESSAGES:
            break
        previous_answer = {"role": "assistant", "text": answer}
        if keep_request:
            previous_answer["caregiver_request"] = request.strip()
        # Only a stated subject age persists. Profile snapshots must not freeze
        # the child's calendar age across later visits to the conversation.
        subject_age = assistant.get("subject_age_override")
        if type(subject_age) in (int, float) and isfinite(subject_age) and subject_age >= 0:
            previous_answer["subject_age_months"] = subject_age
        if assistant.get("response_kind") == "clarification":
            previous_answer["response_kind"] = "clarification"
            # Existing rows predate the structured clarification field. Only
            # these fixed application messages identify an age clarification.
            if assistant.get("clarification_field") == "age" or answer in AGE_CLARIFICATION_MESSAGES:
                previous_answer["clarification_field"] = "age"
        selected[:0] = [{"role": "user", "text": question}, previous_answer]
        characters += pair_size
    return selected


def caregiver_request(question: str, context: list[dict]) -> str:
    """Keep the requested help across short replies without borrowing AI claims."""
    if context and context[-1].get("response_kind") == "clarification":
        if (context[-1].get("clarification_field") == "age"
                and _clarified_age_months(question, context) is not None):
            if context[-1].get("caregiver_request"):
                return context[-1]["caregiver_request"]
            if len(context) >= 2 and context[-2].get("role") == "user":
                return context[-2]["text"]
        return question
    clarification = clarifies_recent_answer(question, context)
    if is_follow_up(question) or clarification:
        if context and context[-1].get("caregiver_request"):
            return context[-1]["caregiver_request"]
        for index in range(len(context) - 1, -1, -1):
            message = context[index]
            if (message["role"] == "user" and not is_follow_up(message["text"])
                    and not clarifies_recent_answer(message["text"], context[:index])
                    and _clarified_age_months(message["text"], context[:index]) is None):
                return message["text"]
    return question


def contextual_retrieval_query(question: str, context: list[dict]) -> str:
    """Use the caregiver's request for search, keeping the current reply intact."""
    request = caregiver_request(question, context)
    return f"{request[:600]}\nFollow-up: {question}" if request != question else question


def contextual_age_months(question: str, context: list[dict]) -> float | None:
    """Use a stated subject age, accepting a short age reply only after clarification."""
    explicit = message_age_months(question)
    if explicit is not None:
        return explicit
    clarified = _clarified_age_months(question, context)
    if clarified is not None:
        return clarified
    query = contextual_retrieval_query(question, context)
    if query != question or (context and is_follow_up(question)
                             and context[-1].get("response_kind") != "clarification"):
        stored_age = context[-1].get("subject_age_months")
        if stored_age is not None:
            return stored_age
        explicit = message_age_months(query)
        if explicit is not None:
            return explicit
    return None


def needs_topic_clarification(question: str, context: list[dict]) -> bool:
    """Separate a missing referent from a meaningful new report about the child."""
    if not is_follow_up(question):
        return False
    words = question.lower().strip()
    if re.match(r"^(?:he|she|they)\b", words) and not re.search(r"\b(?:it|that|this|them|those|these)\b", words):
        return False
    return not context or context[-1].get("response_kind") == "clarification"


def _clarified_age_months(question: str, context: list[dict]) -> float | None:
    if context and context[-1].get("response_kind") == "clarification":
        age_reply = question.strip().rstrip(".!?")
        match = re.fullmatch(
            r"(?:(?:he|she|they|(?:my|our|the) (?:baby|child|infant|toddler)) (?:is|are) )?"
            r"(?P<age>\d+(?:\.\d+)?\s*[- ]?(?:days?|weeks?|months?|years?))"
            r"(?:[- ]old)?(?: please)?", age_reply, re.I,
        )
        if match:
            return message_age_months(f"My baby is {match['age']}")
    return None


def clarifies_recent_answer(question: str, context: list[dict]) -> bool:
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
