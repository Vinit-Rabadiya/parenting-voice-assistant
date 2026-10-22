"""Vaccination routing boundaries while country-specific content awaits review."""
from dataclasses import dataclass
import re

TOPIC = re.compile(r"\b(?:vaccin\w*|immuni[sz]\w*|bcg|ipv|opv|tcv|pentavalent)\b", re.IGNORECASE)
INDIVIDUAL = re.compile(r"\b(?:catch[ -]?up|missed|overdue|contraindicat\w*|allerg\w*|reaction|dose|doses|dosage)\b", re.IGNORECASE)


@dataclass(frozen=True)
class VaccinationDecision:
    answer: str
    reason: str


def inspect_vaccination(question: str) -> VaccinationDecision | None:
    if not TOPIC.search(question):
        return None
    if INDIVIDUAL.search(question):
        return VaccinationDecision(
            "For missed vaccines, doses, allergies or a possible reaction, contact your child's vaccination clinic. "
            "Take their vaccination record so a health professional can assess what is appropriate. "
            "This chat cannot calculate catch-up doses or assess an individual reaction.", "individual_assessment")
    return VaccinationDecision(
        "Kenya-specific vaccination guidance is not yet available from approved references in this chat. "
        "Check your child's vaccination record with their vaccination clinic for current information "
        "and upcoming appointments. This chat cannot confirm which vaccines your child is due to receive.",
        "references_pending_review")
