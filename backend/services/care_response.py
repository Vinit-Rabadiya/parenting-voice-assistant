"""Conservative fallback wording; routing is not evidence or medical triage."""

from dataclasses import dataclass
import re

from backend.services.age import AGE_SCOPE_MESSAGE, message_age_months

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
# Unknown vocabulary is not proof that a request is unrelated. A child keyword
# alone is also not a reason to permit an explicit unrelated task.
UNRELATED = re.compile(
    r"\b(?:repair (?:my |a |the )?car|fix (?:my |a |the )?car|car repair|fix (?:my |a |the )?engine|"
    r"stock prices?|cryptocurrency|weather forecast|coding|programming|"
    r"(?:fix|repair|configure|reset) (?:my |a |the )?(?:internet(?: router)?|router|wi-?fi)|"
    r"write (?:me )?(?:python|javascript) code)\b", re.I)
# Match a requested task, rather than a topic merely mentioned in a care report.
REQUEST_PREFIX = re.compile(
    r"\s*(?:(?:please|also|now|then)\s+)*(?:"
    r"(?:how|where)\s+(?:do|can|could|should)\s+(?:i|we)\s+|"
    r"(?:can|could|would|will)\s+you\s+|"
    r"what(?:'s|\s+is|\s+are)\s+(?:the\s+)?|"
    r"(?:i|we)\s+(?:want|wnt|need|would like)\s+to\s+(?:learn|lern|start)\s+)?",
    re.I,
)
CARE_FOCUS = re.compile(
    r"\b(?:keep|keeping|protect|protecting|comfort|comforting|feed|feeding|dress|dressing|"
    r"soothe|soothing|bathe|bathing|wash|washing|talk to|play with|care for|look after)\s+"
    r"(?:(?:my|our|the|a|your)\s+)?(?:baby|child|infant|toddler)\b|"
    r"\b(?:what|how)\s+(?:should|can|does|do)\s+(?:my|our|the|your)\s+"
    r"(?:baby|child|infant|toddler)\s+(?:wear|eat|drink|sleep|learn|play)\b|"
    r"\b(?:is|are)\b[^.!?\n]{0,60}\b(?:safe|suitable|appropriate)\s+for\s+"
    r"(?:(?:my|our|the|a|your)\s+)?(?:baby|child|infant|toddler)\b|"
    r"\b(?:help|advice|guidance|tips|support)\s+(?:with|on|for|about)\s+"
    + BABY_TOPIC.pattern, re.I)
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
    if UNRELATED.search(message) is None:
        return False
    # Keep genuine care requests such as protecting a baby during car repairs.
    # Incidental mentions ("I have a baby; write Python code") do not qualify.
    # Ambiguous and mixed care requests still receive the model's scope checks.
    explicit_request = False
    for clause in re.split(r"[.!?;,\n]", message):
        unrelated = UNRELATED.search(clause)
        care = CARE_FOCUS.search(clause)
        if care and (unrelated is None or care.start() < unrelated.start()):
            return False
        if unrelated is None and BABY_TOPIC.search(clause) and HEALTH_CONCERN.search(clause):
            return False
        if unrelated and REQUEST_PREFIX.fullmatch(clause[:unrelated.start()]):
            explicit_request = True
    # Uncertain care-related wording goes to the existing contextual model.
    # This fast path is a limited routing rule, not complete intent recognition.
    related_context = (BABY_TOPIC.search(message) or HEALTH_CONCERN.search(message)
                       or message_age_months(message) is not None)
    return explicit_request or not related_context


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
    # A real verb suggesting harm is not a safe automatic spelling correction.
    # Ordinary spelling/grammar interpretation remains with the contextual model.
    if re.search(r"\bbatting\s+(?:my|our|the|a)\s+(?:baby|child|infant)\b", message, re.I):
        return CareResponse("clarification", "Do you mean bathing your baby, or something else? Please clarify the action so I can give suitable guidance.")
    if unresolved_follow_up:
        return CareResponse("clarification", "What were you trying, or what would you like help with? Tell me what is happening with your baby.")
    if clearly_unrelated(message):
        return CareResponse("unrelated", "This chat supports baby care, child development and parenting. I cannot help with that topic here.")
    return None
