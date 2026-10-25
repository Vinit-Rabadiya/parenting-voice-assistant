"""Conservative fallback wording; routing is not evidence or medical triage."""

from dataclasses import dataclass
import re

from backend.services.age import AGE_SCOPE_MESSAGE

@dataclass(frozen=True)
class CareResponse:
    kind: str
    answer: str


BABY_TOPIC = re.compile(
    r"\b(?:baby|babies|child|toddler|newborn|infant|feeding|breastfeed\w*|bottle|"
    r"napp\w*|diaper\w*|bath\w*|teeth\w*|teething|bedtime|crying|milestone\w*|"
    r"crawling|tummy time|weaning|immuni[sz]\w*|vaccin\w*|mealtimes?|meals?|"
    r"picture[ -]?books?|pretend play|taking turns)\b", re.I)
HEALTH_CONCERN = re.compile(
    r"\b(?:fever|temperature|vomit\w*|diarrh\w*|rash|jaundice|reflux|"
    r"cough\w*|constipat\w*|dehydrat\w*|ill|sick|pain|bleed\w*|"
    r"not feeding|won't feed|lost skills|losing skills|stopped walking)\b", re.I)
# Only explicit unrelated requests are rejected; unknown vocabulary is not proof
# that a request is unrelated. A baby-care term takes precedence in mixed text.
UNRELATED = re.compile(
    r"\b(?:repair (?:my |a |the )?car|fix (?:my |a |the )?car|car repair|fix (?:my |a |the )?engine|"
    r"stock prices?|cryptocurrency|weather forecast|"
    r"(?:fix|repair|configure|reset) (?:my |a |the )?(?:internet(?: router)?|router|wi-?fi)|"
    r"write (?:me )?(?:python|javascript) code)\b", re.I)
FOOD_RETENTION = re.compile(
    r"\b(?:cannot|can't|cant|unable to) keep (?:any |even |any of )?(?:the |their |his |her )?"
    r"(?:food|feeds?|milk|fluids?|liquids?|water)(?: down| in)?\b", re.I)
CLINICAL_REQUEST = re.compile(
    r"\b(?:(?:can|could|will|would) you diagnose|diagnose (?:my|why|whether)|"
    r"(?:medicine|medication) dose|(?:calculate|prescribe) (?:a |the |my baby's )?dose)\b", re.I)


def feeding_concern_response(message: str) -> CareResponse | None:
    """Do not turn a possible inability to retain feeds into routine meal tips."""
    normalized = message.replace("\u2019", "'")
    if BABY_TOPIC.search(normalized) and FOOD_RETENTION.search(normalized):
        return CareResponse("professional_referral", "Please contact a health professional promptly about your child being unable to keep food or feeds down. If they cannot keep fluids down, are passing less urine, or seem seriously unwell, seek urgent medical care. This chat cannot assess the cause or severity.")
    return None


def clearly_unrelated(message: str) -> bool:
    return bool(UNRELATED.search(message) and not BABY_TOPIC.search(message)
                and not HEALTH_CONCERN.search(message))


def professional_assessment_response(message: str) -> CareResponse | None:
    """Separate explicit individual assessment requests from general education."""
    feeding = feeding_concern_response(message)
    if feeding is not None:
        return feeding
    if CLINICAL_REQUEST.search(message):
        return CareResponse(
            "professional_referral",
            "This chat cannot diagnose your child or calculate medicine doses. "
            "Please contact a qualified health professional for an individual assessment. "
            "You can describe the baby-care situation to ask for general reference information, "
            "but that does not replace an assessment.",
        )
    return None


def conversation_boundary_response(message: str, *, unresolved_follow_up: bool = False,
                                   child_age_months: float | None = None,
                                   outside_age_range: bool = False) -> CareResponse | None:
    """Apply age/topic boundaries or clarify a missing topic; otherwise generate."""
    if outside_age_range or (child_age_months is not None and child_age_months > 24):
        return CareResponse("age_out_of_scope", AGE_SCOPE_MESSAGE)
    if unresolved_follow_up:
        return CareResponse("clarification", "What would you like more help with? Describe the baby-care situation so I can look for relevant information.")
    if clearly_unrelated(message):
        return CareResponse("unrelated", "This chat supports baby care, child development and parenting. I cannot help with that topic here.")
    return None
