"""Conservative English danger-sign routing; not diagnosis or comprehensive triage."""

from dataclasses import dataclass
import re

from backend.services.age import message_age_months


ESCALATION_MESSAGE = (
    "Your message may describe a danger sign. Seek urgent medical care now at the "
    "nearest health facility. If your child is choking, cannot breathe or is unresponsive, "
    "contact local emergency services immediately. Do not wait for coaching guidance. "
    "This system cannot diagnose the cause or assess how severe it is."
)
SWALLOWED_OBJECT_MESSAGE = (
    "Contact a health professional now about the swallowed object, even if your baby seems comfortable. "
    "If it could be a battery, magnet or sharp object, go to the nearest emergency department immediately. "
    "If your baby is choking, struggling to breathe, cannot swallow or is difficult to wake, "
    "call emergency services now. Do not make your baby vomit. "
    "If available, take a similar object or its packaging to show the clinician."
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
JAUNDICE = {
    "passage_id": "safety-nhs-first-day-yellowing", "source_title": "NHS: Jaundice in babies",
    "pdf_page": None, "source_url": "https://www.nhs.uk/conditions/jaundice-in-babies/",
    "title": "Immediate help: jaundice during the first day of life",
}
URGENT_ILLNESS = {
    "passage_id": "safety-nhs-urgent-child-illness",
    "source_title": "NHS: When to get urgent medical help for babies and children under 5",
    "pdf_page": None,
    "source_url": "https://www.nhs.uk/baby/health/when-to-get-urgent-medical-help-for-babies-and-children-under-5/",
    "title": "Immediate assessment: responsiveness, blue or grey lips and non-fading rash",
}
ANAPHYLAXIS = {
    "passage_id": "safety-who-allergic-airway-swelling",
    "source_title": "WHO: Anaphylaxis as an adverse event following immunization",
    "pdf_page": 2,
    "source_url": "https://cdn.who.int/media/docs/default-source/medicines/pharmacovigilance/anaphylaxis-aefi.pdf",
    "title": "Warning signs: facial swelling and airway symptoms require urgent assessment",
}
EYE_BLEEDING = {
    "passage_id": "safety-nhs-eye-bleeding", "source_title": "NHS: Eye injuries",
    "pdf_page": None, "source_url": "https://www.nhs.uk/conditions/eye-injuries/",
    "title": "Urgent assessment for blood coming from an eye",
}
POISONING = {
    "passage_id": "safety-nhs-poisoning", "source_title": "NHS: Poisoning",
    "pdf_page": None, "source_url": "https://www.nhs.uk/conditions/poisoning/",
    "title": "Immediate assessment after suspected exposure to a harmful substance",
}
BURNS = {
    "passage_id": "safety-nhs-burns-scalds", "source_title": "NHS: Burns and scalds",
    "pdf_page": None, "source_url": "https://www.nhs.uk/conditions/burns-and-scalds/",
    "title": "Prompt assessment for burns and scalds in a young child",
}
SWALLOWED_OBJECT = {
    "passage_id": "safety-aap-swallowed-object", "source_title": "American Academy of Pediatrics: Swallowed foreign object",
    "pdf_page": None, "source_url": "https://www.healthychildren.org/English/tips-tools/Symptom-Checker/Pages/symptomviewer.aspx?symptom=Swallowed+Foreign+Object",
    "title": "Prompt advice for children under two and emergency assessment for high-risk objects or symptoms",
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
    ("heavy_bleeding", r"\b(?:(?:heavy|severe|uncontrolled|uncontrollable) bleeding|bleeding (?:heavily|a lot)|bleeding (?:that )?(?:will not|won't|does not|doesn't) stop|losing a lot of blood|cut (?:that )?(?:will not|won't|does not|doesn't) stop bleeding)\b", INJURY),
    ("poisoning", r"\b(?:poisoned|(?:swallowed|ingested|drank|drunk|ate|eaten) (?:(?:a|an|some|the) )?(?:poison|bleach|detergent|kerosene|paraffin|pesticide|cleaning fluid)|(?:swallowed|had|took|given) too much (?:medicine|medication|paracetamol)|overdos(?:e|ed))\b", POISONING),
    ("swallowed_battery_magnet", r"\b(?:swallowed|swallows|ingested) (?:(?:a|an|the|some|two) )?(?:(?:button|coin|small|strong) )?(?:batter(?:y|ies)|magnets?)\b", INJURY),
    ("swallowed_object", r"\b(?:swallowed|swallows|ingested) (?:(?:a|an|the|some|another|small|plastic|clothing|metal) ){0,3}(?:buttons?(?!\s+batter(?:y|ies)\b)|coins?|beads?|toy(?: parts?)?|objects?|something)\b", SWALLOWED_OBJECT),
    ("burn_scald", r"\b(?:(?:burned|burnt)(?!\s+out\b)|scalded|(?:chemical|electrical|large|deep|severe) burns?|(?:has|have|got|suffered) (?:a )?(?:burn|scald))\b", BURNS),
    ("eye_bleeding", r"\b(?:blood (?:in|from|(?:is )?coming (?:from|out of)) (?:(?:his|her|their|the|(?:my|our|the) (?:baby|child)'s) )?eyes?|bleeding (?:in|from) (?:(?:his|her|their|the|(?:my|our|the) (?:baby|child)'s) )?eyes?|eyes? (?:is |are )?bleeding|bloody tears)\b", EYE_BLEEDING),
    ("facial_airway_swelling", r"\b(?:sw(?:ollen|elling)(?: of)? (?:(?:the|his|her|their) )?(?:face|lips?|tongue|throat)|(?:face|lips?|tongue|throat) (?:is |are |has |have |looks? |become |became |has become |have become )?sw(?:ollen|elling))\b", ANAPHYLAXIS),
    ("abnormal_vomit", r"\b(?:(?:green|yellow-green|bloody) vomit|(?:vomit|vomiting|throwing up) (?:is |looks |looks like )?(?:green|yellow-green|blood)|blood in (?:(?:his|her|their|the) )?vomit)\b", VOMITING),
    ("blue_grey_lips", r"\b(?:(?:blue|grey|gray) (?:lips|tongue)|(?:lips|tongue) (?:are|look|turned|have turned) (?:blue|grey|gray))\b", URGENT_ILLNESS),
    ("non_fading_rash", r"\brash (?:that )?(?:does not|doesn't|will not|won't) fade (?:when (?:i |you )?press(?:ed)?|under pressure)\b", URGENT_ILLNESS),
    ("cannot_keep_fluids", r"\b(?:cannot|can't|cant|unable to) keep (?:any |even |any of )?(?:the |their |his |her )?(?:fluids?|liquids?|water|milk|feeds?) (?:down|in)\b", VOMITING),
    ("breathing", r"\b(?:can(?:not|'t) breathe|not breathing(?!\s+fast\b)|stopped breathing|struggling to breathe|difficulty breathing|difficult breathing|breathing (?:very )?fast|fast breathing|gasping)\b", KENYA),
    ("not_feeding", r"\b(?:(?:cannot|can't|unable to|will not|won't|not able to) (?:drink|feed|breastfeed)|not (?:feeding|drinking|breastfeeding)(?!\s+poorly\b)|(?:feeding|drinking|breastfeeding) poorly)\b", KENYA),
    ("convulsions", r"\b(?:convuls(?:ion|ions|ing)|seizures?)\b", WHO),
    ("unresponsive", r"\b(?:unconscious|unresponsive|lethargic|hard to wake|difficult to wake|cannot wake|can't wake|won't wake|will not wake)\b", WHO),
    ("floppy", r"\b(?:is|are|seems?|became|become|gone|going)\s+(?:very\s+|unusually\s+)?(?:floppy|limp)\b", URGENT_ILLNESS),
    ("dehydration", r"\b(?:dehydrated|dehydration|no wet (?:nappies|diapers)|hasn't (?:peed|urinated)|has not (?:peed|urinated))\b", WHO),
    ("choking", r"\b(?:choking|chokes|choked)\b", WHO),
    ("injury", r"\b(?:(?:fell|fallen) (?:off|from|down)|(?:hit|hurt|injured) (?:his|her|their|the) head|head injury)\b", INJURY),
)
CHILD_CONTEXT = re.compile(r"\b(?:baby|child|infant|newborn|daughter|son|he|she)\b")
CHOKING_PREVENTION_TOPIC = re.compile(
    r"\s+(?:precautions?|prevention|hazards?|risks?|safety(?:\s+(?:tips|advice|guidance))?)\b"
)
ACTIVE_INCIDENT_PREFIX = re.compile(
    r"\b(?:is|are|was|were|started|began|keeps|keep|seems|appears)"
    r"(?:\s+(?:still|now|actually|really|currently|repeatedly|to be)){0,2}\s*$"
)


@dataclass(frozen=True)
class InputSafetyDecision:
    reasons: tuple[str, ...]
    citations: tuple[dict, ...]

    @property
    def escalate(self):
        return bool(self.reasons)

    @property
    def answer(self) -> str:
        # Any additional danger sign retains the immediate emergency response.
        return SWALLOWED_OBJECT_MESSAGE if self.reasons == ("swallowed_object",) else ESCALATION_MESSAGE


def inspect_input(question: str, completed_months: int, *, child_age_days: int | None = None) -> InputSafetyDecision:
    text = question.lower().replace("\u2019", "'")
    text = re.sub(r"\s+", " ", text)
    reasons, citations = [], {}
    if not CHILD_CONTEXT.search(text):
        stated_age = message_age_months(text)
        if stated_age is None or not 0 <= stated_age <= 24:
            return InputSafetyDecision((), ())
    rules = list(RULES)
    if child_age_days == 0:
        rules.append(("first_day_yellowing", r"\b(?:has jaundice|(?:skin|eyes) (?:(?:are|look|looks|appear|appears|seem|seems) )?yellow)\b", JAUNDICE))
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
            prevention = re.search(
                r"\b(?:prevent|preventing|avoid|risk of)"
                r"(?:\s+(?:(?:my|our|the|a|his|her|their)\s+)?(?:baby|child|infant)"
                r"(?:\s+(?:from|getting|being)){0,2})?\s*$", prefix,
            )
            if negated or prevention:
                continue
            # "Choking precautions" names a prevention topic, not an incident.
            # Restrict this exception to the noun phrase at this exact match;
            # another reported danger elsewhere in the message still escalates.
            # Keep malformed/ambiguous active reports conservative as well.
            if (code == "choking" and match.group() == "choking"
                    and CHOKING_PREVENTION_TOPIC.match(text, match.end())
                    and not ACTIVE_INCIDENT_PREFIX.search(prefix)):
                continue
            reasons.append(code)
            citations[source["passage_id"]] = source.copy()
            break
    return InputSafetyDecision(tuple(reasons), tuple(citations.values()))
