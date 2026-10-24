"""Source-checked general education; no individual or national schedule decisions."""
from dataclasses import dataclass
from datetime import date
import re

from backend.services.age import current_date


GENERAL_CHECKED_ON = date(2026, 10, 24)
GENERAL_REVIEW_DAYS = 90

TOPIC = re.compile(r"\b(?:vaccin\w*|immuni[sz]\w*|bcg|ipv|opv|tcv|pentavalent)\b", re.IGNORECASE)
INDIVIDUAL = re.compile(r"\b(?:catch[ -]?up|missed|overdue|contraindicat\w*|allerg\w*|reaction|dose|doses|dosage)\b", re.IGNORECASE)
CURRENT_CONCERN = re.compile(
    r"\b(?:my|our|this)\s+(?:baby|child|infant)\s+(?:has|is|had|seems)|"
    r"\b(?:after|following)\s+(?:the |a |their |his |her )?(?:vaccin\w*|immuni[sz]\w*)|"
    r"\b(?:fever|temperature|rash|swelling|pain|vomit\w*|breathing|crying)\b", re.I)
GENERAL_PURPOSE = re.compile(
    r"\b(?:how (?:do|does) (?:a )?vaccines? work|what (?:are|is) (?:a )?(?:vaccines?|vaccination|immuni[sz]ation)|"
    r"why (?:should|do) (?:i|we) vaccinate|tell me about (?:vaccination|immuni[sz]ation))\b", re.I)
GENERAL_EFFECTS = re.compile(r"\b(?:side[ -]?effects?|expected effects)\b", re.I)
SCHEDULE = re.compile(r"\b(?:schedule|due|which vaccines|what vaccines|when|at \d+ (?:weeks?|months?))\b", re.I)


@dataclass(frozen=True)
class VaccinationDecision:
    answer: str
    reason: str
    source_title: str | None = None
    source_url: str | None = None


def inspect_vaccination(question: str) -> VaccinationDecision | None:
    if not TOPIC.search(question):
        return None
    if INDIVIDUAL.search(question) or CURRENT_CONCERN.search(question):
        return VaccinationDecision(
            "For missed vaccines, doses, allergies or a possible reaction, contact your child's vaccination clinic. "
            "Take their vaccination record so a health professional can assess what is appropriate. "
            "This chat cannot calculate catch-up doses or assess an individual reaction.", "individual_assessment")
    education_current = (not SCHEDULE.search(question)
                         and 0 <= (current_date() - GENERAL_CHECKED_ON).days <= GENERAL_REVIEW_DAYS)
    if education_current and GENERAL_EFFECTS.search(question):
        return VaccinationDecision(
            "Some children have temporary soreness where the injection was given or a mild fever after vaccination. "
            "This general information cannot tell whether a particular child's symptoms are an expected effect. "
            "Contact a health professional if you are concerned about symptoms; seek urgent care if your child seems seriously unwell. "
            "Do not give medicine based on this chat.",
            "general_expected_effects",
            "UNICEF: Vaccines for children — Can a vaccine cause my baby to get sick?",
            "https://www.unicef.org/parenting/health/parents-frequently-asked-questions-vaccines",
        )
    if education_current and GENERAL_PURPOSE.search(question):
        return VaccinationDecision(
            "Vaccines prepare the immune system to recognise and fight particular infections. "
            "They help protect against serious diseases before exposure. Most are given by injection, "
            "while some are given by mouth or through the nose. "
            "For your child's vaccinations in Kenya, take their vaccination record to the clinic to confirm "
            "which vaccines and appointments are appropriate. This chat does not calculate a personal schedule.",
            "general_purpose",
            "WHO: Vaccines and immunization — What is vaccination?",
            "https://www.who.int/news-room/questions-and-answers/item/vaccines-and-immunization-what-is-vaccination",
        )
    return VaccinationDecision(
        "Kenya-specific vaccination guidance is not yet available from approved references in this chat. "
        "Check your child's vaccination record with their vaccination clinic for current information "
        "and upcoming appointments. This chat cannot confirm which vaccines your child is due to receive.",
        "references_pending_review")
