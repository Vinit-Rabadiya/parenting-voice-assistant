"""Conservative English danger-sign routing; not diagnosis or comprehensive triage."""

from dataclasses import dataclass
import re


ESCALATION_MESSAGE = (
    "Your message may describe a danger sign. Seek urgent medical care now at the "
    "nearest health facility. If your child is choking, cannot breathe or is unresponsive, "
    "contact local emergency services immediately. Do not wait for coaching guidance. "
    "This system cannot diagnose the cause or assess how severe it is."
)
KENYA = {
    "passage_id": "c2de5ff8ec6a9d2cebb8", "source_title": "Mother & Child Health Handbook",
    "pdf_page": 45, "source_url": "https://www.health.go.ke/sites/default/files/2023-05/Mother%20Child%20Health%20Handbook%20MOH-FOR%20PRINT.pdf",
    "title": "When to seek care immediately: danger signs",
}
WHO = {
    "passage_id": "safety-who-etat", "source_title": "WHO: Paediatric emergency triage, assessment and treatment",
    "pdf_page": None, "source_url": "https://www.who.int/publications/i/item/9789241510219",
    "title": "Overview: breathing problems, convulsions and severe dehydration",
}
INJURY = {
    "passage_id": "safety-nhs-child-accidents", "source_title": "NHS: What to do if your child has an accident",
    "pdf_page": None, "source_url": "https://www.nhs.uk/baby/first-aid-and-safety/first-aid/what-to-do-if-your-child-has-an-accident/",
    "title": "Child accidents and urgent help (web page, not a PDF)",
}
VOMITING = {
    "passage_id": "safety-nhs-fluid-retention", "source_title": "NHS: Diarrhoea and vomiting",
    "pdf_page": None, "source_url": "https://www.nhs.uk/symptoms/diarrhoea-and-vomiting/",
    "title": "Urgent advice: unable to keep fluids down",
}
FEVER = {
    "passage_id": "safety-nhs-young-infant-temperature",
    "source_title": "NHS: High temperature (fever) in children",
    "pdf_page": None,
    "source_url": "https://www.nhs.uk/symptoms/fever-in-children/",
    "title": "Urgent advice: under three months with a temperature of 38C or higher",
}
URGENT_ILLNESS = {
    "passage_id": "safety-nhs-urgent-child-illness",
    "source_title": "NHS: When to get urgent medical help for babies and children under 5",
    "pdf_page": None,
    "source_url": "https://www.nhs.uk/baby/health/when-to-get-urgent-medical-help-for-babies-and-children-under-5/",
    "title": "Immediate assessment: blue or grey lips and a rash that does not fade under pressure",
}
ANAPHYLAXIS = {
    "passage_id": "safety-who-allergic-airway-swelling",
    "source_title": "WHO: Anaphylaxis as an adverse event following immunization",
    "pdf_page": 2,
    "source_url": "https://cdn.who.int/media/docs/default-source/medicines/pharmacovigilance/anaphylaxis-aefi.pdf",
    "title": "Warning signs: facial swelling and airway symptoms require urgent assessment",
}
CELSIUS = re.compile(r"(?<![\w.,])(?P<value>\d{2}(?:[.,]\d+)?)\s*(?:(?:°|degrees?)\s*)?(?:celsius|c)\b")


def reported_high_infant_temperature(text: str) -> bool:
    """Recognize explicit body readings, not bath/room temperatures or bare numbers."""
    for match in CELSIUS.finditer(text):
        prefix = text[max(0, match.start() - 80):match.start()]
        if re.search(r"\b(?:below|under|less than|not|isn't|is not)\s*$", prefix):
            continue
        if re.search(r"\b(?:bath|water|room|bottle|milk)\b", prefix):
            continue
        if re.search(r"\b(?:temperature|temp|thermometer|baby|child|infant)\b", prefix):
            if float(match["value"].replace(",", ".")) >= 38:
                return True
    return False

# Keep a source per category rather than attributing every rule to a single excerpt.
RULES = (
    ("facial_airway_swelling", r"\b(?:sw(?:ollen|elling)(?: of)? (?:(?:the|his|her|their) )?(?:face|lips?|tongue|throat)|(?:face|lips?|tongue|throat) (?:is |are |has |have |looks? |become |became |has become |have become )?sw(?:ollen|elling))\b", ANAPHYLAXIS),
    ("abnormal_vomit", r"\b(?:(?:green|yellow-green|bloody) vomit|(?:vomit|vomiting|throwing up) (?:is |looks |looks like )?(?:green|yellow-green|blood)|blood in (?:(?:his|her|their|the) )?vomit)\b", VOMITING),
    ("blue_grey_lips", r"\b(?:(?:blue|grey|gray) (?:lips|tongue)|(?:lips|tongue) (?:are|look|turned|have turned) (?:blue|grey|gray))\b", URGENT_ILLNESS),
    ("non_fading_rash", r"\brash (?:that )?(?:does not|doesn't|will not|won't) fade (?:when (?:i |you )?press(?:ed)?|under pressure)\b", URGENT_ILLNESS),
    ("cannot_keep_fluids", r"\b(?:cannot|can't|cant|unable to) keep (?:any |even |any of )?(?:the |their |his |her )?(?:fluids?|liquids?|water|milk|feeds?) (?:down|in)\b", VOMITING),
    ("breathing", r"\b(?:can(?:not|'t) breathe|not breathing(?!\s+fast\b)|stopped breathing|struggling to breathe|difficulty breathing|difficult breathing|breathing (?:very )?fast|fast breathing|gasping)\b", KENYA),
    ("not_feeding", r"\b(?:(?:cannot|can't|unable to|will not|won't|not able to) (?:drink|feed|breastfeed)|not (?:feeding|drinking|breastfeeding)(?!\s+poorly\b)|(?:feeding|drinking|breastfeeding) poorly)\b", KENYA),
    ("convulsions", r"\b(?:convuls(?:ion|ions|ing)|seizures?)\b", WHO),
    ("unresponsive", r"\b(?:unconscious|unresponsive|lethargic|hard to wake|difficult to wake|cannot wake|can't wake|won't wake)\b", WHO),
    ("dehydration", r"\b(?:dehydrated|dehydration|no wet (?:nappies|diapers)|hasn't (?:peed|urinated)|has not (?:peed|urinated))\b", WHO),
    ("choking", r"\b(?:choking|chokes|choked)\b", WHO),
    ("injury", r"\b(?:(?:fell|fallen) (?:off|from|down)|(?:hit|hurt|injured) (?:his|her|their|the) head|head injury)\b", INJURY),
)
CHILD_CONTEXT = re.compile(r"\b(?:baby|child|infant|newborn|daughter|son|he|she)\b")


@dataclass(frozen=True)
class InputSafetyDecision:
    reasons: tuple[str, ...]
    citations: tuple[dict, ...]

    @property
    def escalate(self):
        return bool(self.reasons)


def inspect_input(question: str, completed_months: int) -> InputSafetyDecision:
    text = question.lower().replace("\u2019", "'")
    text = re.sub(r"\s+", " ", text)
    reasons, citations = [], {}
    if not CHILD_CONTEXT.search(text):
        return InputSafetyDecision((), ())
    rules = list(RULES)
    if completed_months < 3:
        rules.append(("young_infant_fever", r"\b(?:fever|feverish|unusually hot|unusually cold)\b", KENYA))
        # Explicit Celsius readings only; do not infer units from a bare number.
        # This extends the existing young-infant referral, not temperature triage
        # for every age, measurement method, hypothetical or historical report.
        if reported_high_infant_temperature(text):
            reasons.append("young_infant_temperature")
            citations[FEVER["passage_id"]] = FEVER.copy()
    for code, pattern, source in rules:
        for match in re.finditer(pattern, text):
            prefix = text[max(0, match.start() - 45):match.start()]
            # Narrow exclusions only: do not suppress a whole question just because
            # it also contains a negated or preventative phrase elsewhere.
            negated = re.search(r"\b(?:no|not|without|isn't|is not|doesn't have|does not have|has no|has not had|not having)(?: an?)?\s*$", prefix)
            prevention = re.search(r"\b(?:prevent|preventing|avoid|risk of)\s*$", prefix)
            if negated or prevention:
                continue
            reasons.append(code)
            citations[source["passage_id"]] = source.copy()
            break
    return InputSafetyDecision(tuple(reasons), tuple(citations.values()))
