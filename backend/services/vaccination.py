"""Source-checked Kenya vaccination education, separate from clinical decisions."""

from dataclasses import dataclass
from datetime import date
import re

from backend.core.config import settings
from backend.services.age import current_date, message_age_months, normalize_age_expressions


GENERAL_CHECKED_ON = date(2026, 10, 28)
SCHEDULE_CHECKED_ON = date(2026, 10, 28)
GENERAL_REVIEW_DAYS = 90


@dataclass(frozen=True)
class VaccinationSource:
    key: str
    title: str
    url: str
    pdf_page: int | None = None


@dataclass(frozen=True)
class VaccinationDecision:
    answer: str
    reason: str
    sources: tuple[VaccinationSource, ...] = ()


SCHEDULER = VaccinationSource(
    "kenya-schedule", "WHO: Kenya vaccination schedule (country-reported data)",
    "https://immunizationdata.who.int/global/wiise-detail-page/vaccination-schedule-for-country_name?ISO_3_CODE=KEN",
)
POLICY = VaccinationSource(
    "kenya-policy", "Kenya Ministry of Health: National Immunization Policy Guidelines 2023",
    "http://guidelines.health.go.ke:8000/media/Kenya_National_Immunization_Policy_Guidelines_Version_signed.pdf",
)
UPDATES = VaccinationSource(
    "kenya-updates", "WHO Kenya Annual Report 2025: immunisation programme updates",
    "https://www.afro.who.int/sites/default/files/2026-04/WHO%20Kenya%20Annual%20Report%202025.pdf", 11,
)
PURPOSE = VaccinationSource(
    "vaccine-purpose", "WHO: Vaccines and immunization - What is vaccination?",
    "https://www.who.int/news-room/questions-and-answers/item/vaccines-and-immunization-what-is-vaccination",
)
EFFECTS = VaccinationSource(
    "vaccine-effects", "UNICEF: Vaccines for children - Your questions answered",
    "https://www.unicef.org/parenting/health/parents-frequently-asked-questions-vaccines",
)
WARNINGS = VaccinationSource(
    "vaccine-warnings", "WHO: Anaphylaxis as an adverse event following immunization",
    "https://cdn.who.int/media/docs/default-source/medicines/pharmacovigilance/anaphylaxis-aefi.pdf", 2,
)
COMFORT = VaccinationSource(
    "vaccine-comfort", "WHO: Five tips for preparing children for vaccination",
    "https://www.who.int/news-room/feature-stories/detail/five-tips-for-preparing-children-for-vaccination",
)

# Programme ages, not a calculator for an individual child's remaining doses.
# The WHO 2025 country report is reconciled with the policy and later updates.
VISITS = (
    ("At birth", 0, "BCG and the birth dose of oral polio vaccine (OPV)."),
    ("6 weeks", 6 * 7 / 30.4375, "OPV 1, pentavalent 1, pneumococcal vaccine (PCV) 1 and rotavirus 1."),
    ("10 weeks", 10 * 7 / 30.4375, "OPV 2, pentavalent 2, PCV 2 and rotavirus 2."),
    ("14 weeks", 14 * 7 / 30.4375, "OPV 3, pentavalent 3, PCV 3, rotavirus 3 and the first inactivated polio vaccine (IPV)."),
    ("6 months", 6, "Malaria vaccine 1 in eligible programme areas."),
    ("7 months", 7, "Malaria vaccine 2 in eligible programme areas."),
    ("9 months", 9, "Measles-rubella (MR) 1, IPV 2 and typhoid conjugate vaccine (TCV); "
     "malaria vaccine 3 in eligible programme areas, and yellow fever vaccine in designated risk areas."),
    ("18 months", 18, "MR 2."),
    ("24 months (second birthday)", 24, "Malaria vaccine 4 in eligible programme areas."),
)
REGIONAL_NOTE = (
    "Malaria and yellow fever vaccines are not offered routinely in every area. "
    "Ask your vaccination clinic to confirm local eligibility and the malaria vaccine product in use."
)
RECORD_NOTE = (
    "Take your child's Mother and Child Health booklet or vaccination record to the clinic. "
    "These routine ages do not show which doses your child has already received or is due for; "
    "the clinic needs their record to confirm the next appointment."
)
INDIVIDUAL_ANSWER = (
    "For missed vaccines, catch-up doses, allergies or a possible reaction, contact your child's vaccination clinic. "
    "Take their vaccination record so a health professional can assess what is appropriate. "
    "This chat cannot calculate catch-up doses, choose a dose or assess an individual reaction. "
    "If your child has trouble breathing, swelling of the face or throat, collapses "
    "or seems seriously unwell, seek urgent medical care."
)
UNAVAILABLE_ANSWER = (
    "Please check your child's Mother and Child Health booklet with their vaccination clinic "
    "for Kenya's current vaccination appointments. The clinic can confirm the right vaccines "
    "using your child's age, vaccination record and local eligibility."
)

TOPIC = re.compile(
    r"\b(?:vaccin\w*|immuni[sz]\w*|bcg|ipv|opv|tcv|pentavalent|pcv\d*|rotavac|rotarix|r21|rts[ ,]?s|jabs?)\b", re.I)
INDIVIDUAL = re.compile(
    r"\b(?:catch[ -]?up|missed|overdue|contraindicat\w*|allerg\w*|reaction|dosage|inject|administer)\b|"
    r"\b(?:give|calculate|prescribe)\b[^.!?\n]{0,40}\b(?:dose|doses|ml|mg)\b", re.I)
CURRENT_CONCERN = re.compile(
    r"\b(?:after|following)\s+(?:the |a |their |his |her )?(?:vaccin\w*|immuni[sz]\w*)|"
    r"\b(?:fever|temperature|rash|swelling|pain|vomit\w*|breathing|crying|unwell|sick)\b", re.I)
GENERAL_PURPOSE = re.compile(
    r"\b(?:how (?:do|does) (?:a )?vaccines? work|what (?:are|is) (?:a )?(?:vaccines?|vaccination|immuni[sz]ation)|"
    r"why (?:should|do) (?:i|we) vaccinate|tell me about (?:vaccination|immuni[sz]ation))\b", re.I)
GENERAL_EFFECTS = re.compile(r"\b(?:side[ -]?effects?|expected effects)\b", re.I)
SCHEDULE = re.compile(
    r"\b(?:schedule|due|which vaccines|what vaccines|when|at birth|newborn|days?|weeks?|months?|years?|"
    r"appointments?|next|how many|doses?)\b", re.I)
REQUESTED_AGE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(days?|weeks?|months?|years?)\b", re.I)
PLANNING_PERIOD = re.compile(r"\b(?:next|coming|following|cover|covers|covering)\s+(?:the\s+)?(\d+(?:\.\d+)?)\s*(days?|weeks?|months?|years?)\b", re.I)
OPTIONAL_REQUEST = re.compile(r"\b(?:optional|additional|private|hepatitis[ -]?b|hep[ -]?b)\b", re.I)
COMFORT_REQUEST = re.compile(r"\b(?:baby[ -]friendly|alternatives?|less painful|gentler|comfort)\b", re.I)

# Purpose descriptions come from the policy's antigen chapters, not model output.
VACCINES = (
    (r"\bbcg\b", "BCG helps protect young children against severe forms of tuberculosis (TB)."),
    (r"\b(?:opv|ipv|polio)\b", "OPV (oral drops) and IPV (an injection) protect against polio, a disease that can cause paralysis."),
    (r"\b(?:pentavalent|penta|dtp|dpt)\b", "Pentavalent combines protection against diphtheria, tetanus, whooping cough (pertussis), hepatitis B and Haemophilus influenzae type b (Hib)."),
    (r"\b(?:pcv\d*|pneumococcal)\b", "Pneumococcal conjugate vaccine (PCV) helps protect against pneumococcal infections, including pneumonia, meningitis and bloodstream infection."),
    (r"\b(?:rotavirus|rotavac|rotarix)\b", "Rotavirus vaccination helps protect against severe diarrhoea caused by rotavirus. "
     "The routine three-dose series is at 6, 10 and 14 weeks. Rotarix uses a different, two-dose series; "
     "the clinic must check the product and doses recorded before advising an individual child."),
    (r"\b(?:measles|rubella|mr)\b", "Measles-rubella (MR) protects against measles and rubella."),
    (r"\b(?:typhoid|tcv)\b", "Typhoid conjugate vaccine (TCV) protects against typhoid fever. It is included in Kenya's routine schedule at 9 months."),
    (r"\byellow fever\b", "Yellow fever vaccine protects against yellow fever. Kenya's routine schedule lists it at 9 months in designated risk areas. " + REGIONAL_NOTE),
    (r"\b(?:malaria|r21|rts[ ,]?s)\b", "Malaria vaccination helps protect against malaria and is offered in eligible programme areas. "
     "Kenya's routine programme lists visits at 6, 7, 9 and 24 months. " + REGIONAL_NOTE + " Continue using an insecticide-treated mosquito net; vaccination does not replace other malaria prevention."),
)


def _current(checked_on: date) -> bool:
    return 0 <= (current_date() - checked_on).days <= GENERAL_REVIEW_DAYS


def _quantity_months(match) -> float:
    number, unit = match.groups()
    return float(number) * {"day": 1 / 30.4375, "week": 7 / 30.4375,
                            "month": 1, "year": 12}[unit.lower().rstrip("s")]


def _additional_information(question: str) -> tuple[str, tuple[VaccinationSource, ...]]:
    notes, sources = [], []
    if OPTIONAL_REQUEST.search(question):
        notes.append("Additional vaccines: The routine pentavalent vaccine includes hepatitis B protection. "
                     "This schedule is not an exhaustive list of additional vaccines available privately or for travel. "
                     "Ask your vaccination clinic about additional options appropriate to your child's age, "
                     "health and travel plans; this chat cannot confirm a personalised optional-vaccine schedule.")
        sources.extend((POLICY, PURPOSE))
    if COMFORT_REQUEST.search(question):
        notes.append("For a gentler vaccination visit, hold your baby close and, if breastfeeding, "
                     "ask about breastfeeding during vaccination. These comfort measures do not replace vaccines. "
                     "Ask the clinic before changing vaccine products or timing.")
        sources.extend((COMFORT, PURPOSE))
    return "\n\n".join(notes), tuple(dict.fromkeys(sources))


def _schedule_answer(question: str, child_age_months: float | None, *, topic: str | None = None) -> str:
    """Use the profile age by default; programme ages never establish due doses."""
    normalized = normalize_age_expressions(question)
    contextual = normalize_age_expressions(topic or question)
    period = PLANNING_PERIOD.search(normalized) or PLANNING_PERIOD.search(contextual)
    # An elapsed planning interval is not the child's age or a single visit age.
    age_text = PLANNING_PERIOD.sub("", normalized)
    requested_age = message_age_months(age_text)
    if requested_age is None:
        quantities = list(REQUESTED_AGE.finditer(age_text))
        if len(quantities) == 1:
            requested_age = _quantity_months(quantities[0])
    planning_age = requested_age if requested_age is not None else child_age_months
    if planning_age is None:
        planning_age = message_age_months(PLANNING_PERIOD.sub("", contextual))
    overview = re.search(r"\b(?:full|complete|entire|overview|from|through|between)\b|\b(?:0|birth)\s*(?:-|to)", question, re.I)
    if overview:
        requested_age = None
    elif re.search(r"\b(?:birth|new[ -]?born)\b", question, re.I):
        requested_age = 0
    named = [pattern for pattern, _ in VACCINES if re.search(pattern, question, re.I)]
    visits = [visit for visit in VISITS if requested_age is not None and abs(visit[1] - requested_age) < 0.01]
    heading = "Kenya's routine vaccination visits from birth through the second birthday:"
    if not visits:
        if requested_age is not None and not overview:
            earlier = [visit for visit in VISITS if visit[1] <= requested_age]
            later = [visit for visit in VISITS if visit[1] > requested_age]
            visits = earlier[-1:] + later[:1]
            heading = "Kenya's routine visits around the age you asked about:"
        else:
            visits = VISITS
    elif requested_age == 0:
        heading = "Kenya's routine birth vaccines are:"
    else:
        heading = "For the age you asked about, Kenya's routine schedule lists:"
    if period:
        if planning_age is None:
            return "How old is the baby you are planning for? I need their age to show the visits in that period."
        end_age = min(24, planning_age + _quantity_months(period))
        visits = [visit for visit in VISITS if planning_age - 0.01 <= visit[1] <= end_age + 0.01]
        age_days = planning_age * 30.4375
        age_label = ("birth" if planning_age == 0
                     else f"{age_days:g} {'day' if abs(age_days - 1) < 0.0001 else 'days'}" if planning_age < 1
                     else f"{planning_age:g} {'month' if planning_age == 1 else 'months'}")
        heading = f"Routine vaccination visits over the next {period[1]} {period[2].lower()}, starting from {age_label}:"
        if planning_age + _quantity_months(period) > 24:
            heading += " This list stops at the second birthday."
    elif requested_age is None and child_age_months is not None and not overview and not named:
        # Show surrounding programme visits, not a claim that the earlier doses
        # were received or that the next dose is due. Age alone cannot tell that.
        earlier = [visit for visit in VISITS if visit[1] <= child_age_months]
        later = [visit for visit in VISITS if visit[1] > child_age_months]
        visits = earlier[-1:] + later[:1]
        heading = "Kenya's routine visits around your child's age:"
    if re.search(r"\bipv\b", question, re.I) and not re.search(r"\bopv\b", question, re.I):
        named = [r"\bipv\b|inactivated polio"]
    elif re.search(r"\bopv\b", question, re.I) and not re.search(r"\bipv\b", question, re.I):
        named = [r"\bopv\b|oral polio"]
    if named and not overview:
        selected = [visit for visit in visits if any(re.search(pattern, visit[2], re.I) for pattern in named)]
        if selected or period:
            visits = selected
        elif not period:
            visits = [visit for visit in VISITS if any(re.search(pattern, visit[2], re.I) for pattern in named)]
            heading = "Kenya's routine timing for the vaccine you asked about:"
    age_note = ""
    if requested_age is None and child_age_months is not None and not period:
        age_note = f"Your child's recorded age is {child_age_months:.1f} months. "
    lines = "\n".join(f"- {label}: {vaccines}" for label, _, vaccines in visits)
    if not visits:
        lines = "No routine visit ages in the reference schedule fall within this period. Check the vaccination record with the clinic for individual appointments."
    return f"{age_note}{heading}\n{lines}\n\n{REGIONAL_NOTE}\n\n{RECORD_NOTE}"


def inspect_vaccination(question: str, child_age_months: float | None = None, *,
                        topic: str | None = None) -> VaccinationDecision | None:
    """Use current wording for intent/symptoms; context only supplies the topic."""
    if not TOPIC.search(question) and not (topic and TOPIC.search(topic)):
        return None
    question = question.replace("\u2019", "'")
    concern_text = re.sub(r"\byellow fever\b", "", question, flags=re.I)
    if INDIVIDUAL.search(question) or (CURRENT_CONCERN.search(concern_text) and not GENERAL_EFFECTS.search(question)):
        return VaccinationDecision(INDIVIDUAL_ANSWER, "individual_assessment")
    if GENERAL_EFFECTS.search(question) and _current(GENERAL_CHECKED_ON):
        # A symptom report must not become reassurance merely because effects were asked about.
        report = re.search(r"\b(?:my|our|this|he|she|they|his|her|their)\b|\bafter\b", question, re.I)
        if report and CURRENT_CONCERN.search(concern_text):
            return VaccinationDecision(INDIVIDUAL_ANSWER, "individual_assessment")
        return VaccinationDecision(
            "Temporary soreness at the injection site or a mild fever can occur after vaccination. "
            "You can use a cool cloth on a sore injection site. Ask a health professional before giving medicine. "
            "If symptoms concern you or persist, contact your child's clinic. Trouble breathing, swelling of the face "
            "or throat, collapse or becoming seriously unwell need urgent medical care. "
            "A symptom happening after vaccination does not by itself show that the vaccine caused it.",
            "general_expected_effects", (EFFECTS, WARNINGS, POLICY),
        )
    if SCHEDULE.search(question) or (topic and SCHEDULE.search(topic) and (
        OPTIONAL_REQUEST.search(question) or COMFORT_REQUEST.search(question)
    )):
        if not settings.KENYA_VACCINATION_SCHEDULE_ENABLED or not _current(SCHEDULE_CHECKED_ON):
            return VaccinationDecision(UNAVAILABLE_ANSWER, "schedule_unavailable")
        if re.search(r"\brotarix\b", question, re.I):
            return VaccinationDecision(
                "Rotarix uses a two-dose series, normally at 6 and 10 weeks. "
                "Kenya's currently reported rotavirus programme uses a three-dose series at 6, 10 and 14 weeks. "
                "The clinic must check the vaccine product and previous doses in your child's record "
                "before advising what they need next.", "vaccine_purpose", (POLICY, SCHEDULER),
            )
        additional, sources = _additional_information(question)
        answer = _schedule_answer(question, child_age_months, topic=topic)
        return VaccinationDecision(answer + ("\n\n" + additional if additional else ""),
                                   "routine_schedule", tuple(dict.fromkeys((SCHEDULER, UPDATES, *sources))))
    named_topic = question if TOPIC.search(question) else topic or question
    named = [text for pattern, text in VACCINES if re.search(pattern, named_topic, re.I)]
    if named:
        if not settings.KENYA_VACCINATION_SCHEDULE_ENABLED or not _current(SCHEDULE_CHECKED_ON):
            return VaccinationDecision(UNAVAILABLE_ANSWER, "schedule_unavailable")
        return VaccinationDecision("\n\n".join(named) + "\n\n" + RECORD_NOTE,
                                   "vaccine_purpose", (POLICY, SCHEDULER, UPDATES))
    if GENERAL_PURPOSE.search(question) and _current(GENERAL_CHECKED_ON):
        return VaccinationDecision(
            "Vaccines train the immune system to recognise and fight particular infections. "
            "They help protect children against serious diseases before exposure. "
            "Most are injections; some are given by mouth. "
            "Follow the appointments recorded in your child's Mother and Child Health booklet, "
            "and ask the vaccination clinic about anything that is unclear.",
            "general_purpose", (PURPOSE,),
        )
    # Other education uses the existing contextual generation path, not extra model calls.
    return None
