"""Limited English caregiver-support routing; no diagnosis or automatic reporting."""

from dataclasses import dataclass
import re

from backend.services.kenya_contacts import emergency_resources


SELF_HARM = re.compile(
    r"\b(?:kill(?:ing)? myself|hurt(?:ing)? myself|harm(?:ing)? myself|end(?:ing)? my life|take my own life|"
    r"i want to die|i don't want to live|i wish i (?:was|were) dead|suicidal|self[- ]harm)\b", re.I,
)
CHILD_HARM = re.compile(
    r"\b(?:(?:hurt(?:ing)?|harm(?:ing)?|hit(?:ting|s)?|shak(?:es?|ing)|kill(?:ing)?|abus(?:e|ing)) (?:my|the|our) (?:baby|child|infant)|"
    r"(?:baby|child|infant) (?:is being|was|is) (?:hit|hurt|abused|shaken))\b", re.I,
)
DISTRESS = re.compile(
    r"\b(?:i (?:have|think i have|may have|might have) (?:postpartum|postnatal) depression|i (?:feel|am feeling) (?:hopeless|worthless)|"
    r"i can't cope|i cannot cope|i (?:can't|cannot) bond with my baby|"
    r"i (?:feel|am feeling|have felt) depressed since (?:giving birth|having my baby))\b", re.I,
)
NEGATION = re.compile(r"\b(?:not|never|don't|do not|not going to|don't want to|do not want to|no thoughts of|prevent|preventing|risk of)\s*$", re.I)

# Each contact records its verification date. Contacts are shown only for selected Kenya;
# availability is not checked in real time and these are not emergency guarantees.
BEFRIENDERS = {
    "label": "+254 722 178177", "url": "tel:+254722178177?oai_link_source=model_response_hotline",
    "service": "Befrienders Kenya Suicide Prevention Helpline", "country": "KE",
    "availability": "Monday to Friday, 9 am to 5 pm; not a 24-hour emergency service.",
    "source_url": "https://www.facebook.com/befrienderskenya/?oai_link_source=model_response_hotline",
    "verified_on": "2026-10-20",
}
CHILDLINE = {
    "label": "116", "url": "tel:116", "service": "Kenya National Child Helpline",
    "country": "KE", "availability": "24 hours a day, according to the service directory.",
    "source_url": "https://childrenservices.go.ke/services", "verified_on": "2026-10-20",
}
@dataclass(frozen=True)
class CrisisDecision:
    kind: str | None
    reasons: tuple[str, ...]
    answer: str
    resources: tuple[dict, ...]


def active_match(pattern, text):
    for match in pattern.finditer(text):
        prefix = text[max(0, match.start() - 45):match.start()]
        if not NEGATION.search(prefix):
            return True
    return False


def inspect_crisis(question: str, support_country: str | None = None) -> CrisisDecision:
    text = re.sub(r"\s+", " ", question.lower().replace("\u2019", "'"))
    self_harm = active_match(SELF_HARM, text)
    child_harm = active_match(CHILD_HARM, text)
    distress = active_match(DISTRESS, text)
    if not (self_harm or child_harm or distress):
        return CrisisDecision(None, (), "", ())
    reasons = tuple(code for code, matched in (
        ("self_harm_concern", self_harm), ("child_safety_concern", child_harm),
        ("caregiver_distress", distress),
    ) if matched)
    urgent = self_harm or child_harm
    if urgent:
        answer = (
            "I'm sorry you are facing this. Your safety and your child's safety matter. "
            "If anyone may be hurt now, contact local emergency services or go to the nearest "
            "emergency department. If you can do so safely, ask a trusted person to stay with "
            "you and help keep your child safe. Do not wait for a coaching answer."
        )
    else:
        answer = (
            "I'm sorry things feel difficult. You deserve support. Please speak with a "
            "health professional about how you are feeling, and consider asking someone "
            "you trust for practical support. This message cannot diagnose depression. "
            "If you or your child may be harmed, seek urgent help through local emergency "
            "services or the nearest emergency department."
        )
    resources = []
    if support_country == "KE":
        if urgent:
            resources.extend(emergency_resources(support_country))
        if self_harm or distress:
            resources.append(BEFRIENDERS.copy())
        if child_harm:
            resources.append(CHILDLINE.copy())
    return CrisisDecision("crisis_support" if urgent else "caregiver_support", reasons, answer, tuple(resources))
