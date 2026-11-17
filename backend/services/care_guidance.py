"""Source-checked basic-care support and bounded answer checks, not medical triage."""

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
import json
from math import isfinite
from pathlib import Path
import re
from urllib.parse import urlsplit

from backend.services.conversation_context import caregiver_request
from backend.services.retrieval import RetrievedPassage


REFERENCE_PATH = Path(__file__).resolve().parents[2] / "data/common-care-guidance.json"
TOPICS = {
    "food_flavours": r"\b(?:chill(?:i|ies)|chili(?:es)?|spic(?:e|es|y)|hot sauce|hot peppers?)\b",
    "reflux": r"\b(?:reflux|regurgitat\w*|spit(?:s|ting)? up|spitting)\b|\b(?:milk|feeds?)\b.{0,45}\b(?:comes? back|coming back|dribbles? back|back up|brought up)\b|\bbring(?:s|ing)? up\b.{0,25}\bmilk\b|\bbrings? (?:some )?milk back\b",
    "nappy_rash": r"\b(?:nappy|diaper)[ -]?(?:area )?(?:rash|soreness|irritation)\b|\b(?:bottom|nappy area|diaper area)\b.{0,30}\b(?:sore|red|irritated)\b|\b(?:sore|red|irritated)\b.{0,55}\b(?:bottom|nappy area|diaper area)\b",
    "sleep": r"\b(?:sleep|sleeping|bedtime|night waking)\b|\bwake[sn]?\b.{0,70}\b(?:night|often|cot|crib)\b|\bwaking\b.{0,25}\bnight\b|\bsettl\w*\b.{0,30}\b(?:night|cot|crib)\b",
    "feeding": r"\b(?:food|foods|meals?|feeding|breastfeed\w*|formula|mealtime|recipes?)\b",
    "stomach_upset": r"\b(?:vomit\w*|diarrh[oe]+a|(?:loose|watery) (?:stools?|poo)|being sick)\b",
    "fever": r"\b(?:fever|high temperature|thermometer)\b|\b(?:baby|child)\b.{0,20}\bfeels? hot\b",
    "cough_cold": r"\b(?:cough\w*|runny nose|blocked nose|stuffy nose|a cold|has a cold)\b",
    "teething": r"\b(?:teething|sore gums?|gum (?:pain|discomfort)|tooth coming|teeth (?:coming|come through))\b|\bsooth\w*\s+(?:(?:my|their|the|sore)\s+)?gums?\b",
    "stools": r"\b(?:constipat\w*|hard (?:poo|stool)|painful stools?|stool changes?)\b",
    "jaundice": r"\b(?:jaundice|yellow(?:ing)? (?:skin|eyes)|eyes (?:are |look )?yellow)\b",
    "oral_care": r"\b(?:brush\w*.{0,20}teeth|clean\w*.{0,20}teeth|toothbrush|toothpaste|dental care)\b",
    "outings": r"\b(?:sunshine|sun safety|direct sun|outdoor|sunhat|hot weather|outing|going outside)\b",
    "records": r"\b(?:health record|growth record|clinic visit|health review|clinic appointment|growth chart)\b",
    "soothing": r"\b(?:crying|cries|sooth\w*|comfort\w*)\b",
    "behaviour": r"\b(?:tantrum\w*|frustrat\w*|big feelings)\b",
    "development_concern": r"\b(?:lost (?:a |an |the |their )?(?:skill|ability)|stopped (?:talking|walking|babbling)|developmental (?:concern|delay)|development concern|not reaching milestones)\b",
    "birthday": r"\b(?:second birthday|turn(?:s|ing)? two|2nd birthday)\b",
    "teething_illness": r"\bteething\b.{0,70}\b(?:diarrh[oe]+a|loose stools?|fever|vomit\w*)\b|\b(?:diarrh[oe]+a|loose stools?|fever|vomit\w*)\b.{0,70}\bteething\b",
    "food_refusal": r"\b(?:fussy eat\w*|picky eat\w*|refus\w*.{0,25}(?:solids|food)|(?:food|solids).{0,25}refus\w*)\b",
    "food_storage": r"\b(?:foods?|snacks?|fruit|vegetables?|meals?|lunch)\b[\s\S]*\b(?:refrigerat\w*|cool bag|cool box|overnight|night before|pack\w*|portable|storing|storage)\b|\b(?:pack\w*|storing|storage|refrigerat\w*)\b[\s\S]*\b(?:foods?|snacks?|fruit|vegetables?|meals?|lunch)\b",
    "cup_drinking": r"\b(?:open cup|free-flow cup|drink\w* from (?:an? |the )?cup)\b",
    "cradle_cap": r"\bcradle[ -]cap\b",
    "cord_safety": r"\b(?:curtain|blind|window)[ -]cords?\b|\bcords? (?:from|on) (?:the )?(?:blinds?|curtains?)\b",
    "occupied_play": r"\bkeep (?:him|her|them|(?:my|our|the) (?:child|baby|toddler)) (?:busy|occupied|entertained)\b",
}
HEALTH_TOPICS = {"reflux", "nappy_rash", "stomach_upset", "fever", "cough_cold", "teething", "teething_illness", "stools", "jaundice", "development_concern", "cradle_cap"}
_DENIED_SYMPTOM_PREFIX = re.compile(
    r"\b(?:no|not|without|isn['\u2019]t|aren['\u2019]t|doesn['\u2019]t|don['\u2019]t|hasn['\u2019]t|haven['\u2019]t)"
    r"(?:\s+(?:have|has|had|having|show|shows|showing|a|an|any|current|new|longer|signs?|of))*\s+"
    r"(?:(?:fevers?|cough\w*|cold|vomit\w*|diarrh[oe]+a|pain|jaundice|rash)"
    r"(?:\s*,\s*|\s+(?:or|and|nor)\s+))*$", re.I,
)
INTERACTION = re.compile(r"\b(?:talk|talking|communicat\w*|language|sing|singing|bond|bonding|pretend|teddy|doll)\b", re.I)
FOOD_IDEAS = re.compile(r"\b(?:(?:what|which) (?:(?:soft|first|finger|family|healthy) )?foods?|meal ideas?|food ideas?|recipes?|cook|cooking|prepare|make for|serve)\b", re.I)
SCHEDULE_REQUEST = re.compile(r"\b(?:how often|how many (?:times|meals|feeds|snacks)|schedule|timetable|frequency|times (?:a|per) day)\b", re.I)
AMOUNT_REQUEST = re.compile(r"\b(?:how much|amounts?|quantity|quantities|portion|serving size|recipes?|ingredients?)\b", re.I)
TIMING_REQUEST = re.compile(r"\b(?:how long|how much sleep|how many hours|what time|when should|schedule|timetable|minutes?|hours?)\b", re.I)
NUMBER = r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|half|quarter|twice|thrice)"
MEAL_SCHEDULE = re.compile(rf"\b{NUMBER}(?:\s+to\s+{NUMBER})?\s+(?:(?:small|main|regular|nutritious)\s+)?(?:meals?|feeds?|snacks?|eating occasions|times\s+(?:a|per)\s+day)\b|\b(?:twice|thrice) (?:a|per) day\b", re.I)
FOOD_AMOUNT = re.compile(rf"\b{NUMBER}(?:\s+to\s+{NUMBER})?\s+(?:a\s+)?(?:table\s?spoons?|tea\s?spoons?|spoonfuls?|cups?|grams?)\b", re.I)
TREATMENT_PRODUCT = re.compile(r"\b(?:apply(?:ing)?|us(?:e|ing)|try(?:ing)?|spread(?:ing)?|put(?:ting)?|recommend(?:ing)?|giv(?:e|ing)|add(?:ing)?|switch(?:ing)?)\b[^.!?\n]{0,90}\b(?:zinc oxide|hydrocortisone|steroids?|antifungals?|antibiotics?|medicated|creams?|ointments?|lotions?|thickeners?|thickened formula|anti[- ]reflux formula|hypoallergenic formula|probiotics?|gripe water|laxatives?|decongestants?|cough syrup|teething gels?)\b", re.I)
FEED_CHANGE = re.compile(r"\b(?:smaller (?:amounts|feeds)|more (?:often|frequent(?:ly)?)|frequent(?:ly)?[^.!?\n]{0,70}\b(?:feeds?|meals?|amounts?)|(?:reduce|reducing)\b[^.!?\n]{0,35}\b(?:feed|milk))\b", re.I)
CARE_DURATION = re.compile(rf"\b{NUMBER}(?:\s*(?:-|to)\s*{NUMBER})?\s+(?:(?:a|an)\s+)?(?:minutes?|hours?|days?|weeks?)\b(?!\s*[- ]?old\b)", re.I)
OFF_TOPIC_ACTIVITY = re.compile(r"\b(?:talk|chat|sing) (?:with|to) (?:your |the )?(?:baby|child|toddler)|\b(?:language development|naming foods|name (?:the |different )?foods)\b", re.I)
REFERRAL = re.compile(r"\b(?:health (?:worker|professional|facility)|doctor|clinician|clinic|medical (?:care|advice|assessment))\b", re.I)
SAFE_SLEEP = re.compile(r"\bback\b.{0,100}\bflat\b|\bflat\b.{0,100}\bback\b", re.I | re.S)
UNSAFE_SLEEP = re.compile(r"\b(?:put|place|let|lay)\b[^.!?\n]{0,55}\b(?:sleep|sleeping)\b[^.!?\n]{0,25}\b(?:side|front|tummy|stomach|upright|inclined|seated)\b|\b(?:raise|elevate|incline)\b[^.!?\n]{0,45}\b(?:cot|mattress|bed)\b", re.I)
EARLY_SOLIDS = re.compile(r"\b(?:give|offer|start|introduce|feed|try|serve|add|mix|put)\b[^.!?\n]{0,55}\b(?:porridge|puree|mashed|solids?|rice|water|juice|honey|cereal)\b", re.I)


def positive_match(pattern: re.Pattern, answer: str) -> bool:
    return any(not re.search(r"\b(?:do not|don't|never|avoid|not)\s*$", answer[max(0, m.start() - 20):m.start()], re.I)
               for m in pattern.finditer(answer))


@lru_cache(maxsize=1)
def load_references():
    data = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("review_kind") != "source_checked_basic_care_not_clinical_validation":
        raise ValueError("Unsupported basic-care reference pack.")
    date.fromisoformat(data["checked_on"])
    for source in data["sources"].values():
        url = urlsplit(source["url"])
        if (url.scheme != "https" or url.hostname not in {"www.nhs.uk", "www.unicef.org", "healthiertogether.westlondon.nhs.uk", "www.gov.uk"}
                or url.username or url.password or not source["publisher"] or not source["title"]):
            raise ValueError("Invalid basic-care source.")
    ids = set()
    for entry in data["entries"]:
        if (entry["id"] in ids or entry["topic"] not in TOPICS
                or not 0 <= entry["min_months"] < entry["max_months_exclusive"] <= 25):
            raise ValueError("Invalid basic-care scope.")
        ids.add(entry["id"])
        for reference in entry["references"]:
            if reference["source"] not in data["sources"] or not reference["section"] or not reference["text"].strip():
                raise ValueError("Basic-care references require traceable sections and text.")
        if sum(len(r["text"].split()) for r in entry["references"]) > 160:
            raise ValueError("Basic-care fallback exceeds the response limit.")
    return data


@dataclass(frozen=True)
class CareGuidance:
    topic: str
    references: list[RetrievedPassage]
    food_ideas: bool
    allow_schedule: bool
    allow_amount: bool
    infant: bool
    first_solids: bool
    milk_only: bool
    allow_timing: bool
    overnight_storage: bool
    caregiver_one_handed: bool

    @property
    def fallback(self):
        return "\n\n".join(reference.text for reference in self.references)

    @property
    def instructions(self):
        rules = ["Answer the caregiver's request directly using these selected care facts; do not add unrelated activities."]
        if self.topic == "feeding":
            if not self.allow_schedule:
                rules.append("Do not supply a meal or feeding schedule: none was requested.")
            if not self.allow_amount:
                rules.append("Do not supply feeding quantities: none were requested.")
            if self.food_ideas:
                rules.append("Give food examples; do not add talking, singing or play activities.")
        if self.topic == "food_flavours":
            rules.append("Distinguish mild herbs/spices from very hot chilli. Follow the selected source on gradual introduction and the child's tolerance. Do not invent a universal age or time of day for chilli, or claim it damages an immature digestive system.")
            rules.append("The selected source establishes no chilli quantity, frequency or clock time. Do not recommend pinches, spoonfuls, once-a-day use, morning/afternoon use or a bedtime interval. If asked when, explain that no special feeding time is established by this guidance; discuss gradual flavour introduction without prescribing a schedule.")
        if self.topic == "food_storage":
            rules.append("Keep all packing and cooling constraints from this conversation. Cooked foods and pre-cut fruit/vegetables need cold storage and an insulated bag with ice packs during transport; a sealed ordinary bag does not keep them safe overnight. Distinguish whole uncut fruit: a whole banana does not need the same refrigeration as cut or cooked food. With no cooling, suggest whole soft fruit prepared only when served, not raw hard apple/carrot pieces. Answer advance-packing questions directly; do not invent storage time limits or say all whole fruit is unsafe without refrigeration.")
        if self.topic == "cup_drinking":
            rules.append("Discuss drinking practice with safe drinking water and a clean cup only. Do not introduce bath-water play, bath-water drinking or a separate play activity. Let the child set the pace without forced drinking.")
        if self.topic == "cradle_cap":
            rules.append("Explain gentle scalp care and the selected assessment signs, without confirming a diagnosis. Do not choose oils, creams or medicines; a pharmacist can advise on suitable products.")
        if self.topic == "cord_safety":
            rules.append("Keep cords out of reach and climbing furniture away from windows. Do not invent safety-device mechanisms or installation steps, or promise that any device eliminates strangulation risk.")
        if self.topic == "occupied_play":
            rules.append("The caregiver is doing another task nearby. Use large safe objects with a dry empty container, or a sturdy baby book. Do not suggest water play, tear-and-paste crafts, glue or small objects. Pause the caregiver's task whenever the child needs help; do not suggest leaving the child alone.")
            if self.caregiver_one_handed:
                rules.append("The caregiver needs a one-handed option. Keep their other hand free; do not say they can use both hands. This restriction does not apply to the child's hands.")
        if self.topic in HEALTH_TOPICS:
            rules.append("Give basic care and conditional assessment advice. Do not select creams, active ingredients or treatment durations.")
        if self.topic in {"reflux", "cough_cold"}:
            rules.append("Do not change feed amounts or frequency; individual feeding changes need professional advice.")
        if self.topic == "nappy_rash":
            rules.append("Include assessment for rash with fever, worsening or persistent symptoms; do not assume fever is present.")
        if self.topic == "teething_illness":
            rules.append("Do not suggest that teething, drooling or swallowed saliva explains diarrhoea, vomiting or fever.")
        if self.topic == "sleep" and not self.allow_timing:
            rules.append("Do not add sleep-hour targets or timed bedtime steps: none were requested.")
        if self.infant and self.topic == "sleep":
            rules.append("Use the supplied quiet settling and clear-cot facts. Do not recommend warming a cot or mattress with heating pads or hot-water bottles, or invent a required deep-sleep waiting interval.")
        if self.infant and self.topic in {"reflux", "sleep"}:
            rules.append("Keep the distinction between upright awake care and sleeping flat on the back.")
        return "\n".join(rules)

    def findings(self, answer: str) -> tuple[str, ...]:
        reasons = []
        if self.topic == "food_storage":
            if not re.search(r"\b(?:chill\w*|refrigerat\w*|cold|cool bag|cool box|ice packs?)\b", answer, re.I):
                reasons.append("missing_food_cooling_precaution")
            if self.overnight_storage and not re.search(r"\b(?:do not|don't|cannot|can't|avoid|never|not safe|unsafe|no)\b[^.!?\n]{0,110}\b(?:overnight|night before|room temperature|unrefrigerated|ordinary bag)\b|\b(?:overnight|night before|room temperature|unrefrigerated)\b[^.!?\n]{0,110}\b(?:not|unsafe|cannot|can't)\b", answer, re.I):
                reasons.append("missing_overnight_storage_boundary")
            if re.search(r"\b(?:whole (?:uncut )?fruit|whole (?:ripe )?banana)\b[^.!?\n]{0,100}\b(?:unsafe|not safe|requires? refrigeration|needs? cooling)\b", answer, re.I):
                reasons.append("unsupported_whole_fruit_restriction")
        if self.topic == "cup_drinking" and re.search(r"\b(?:bath\w*|tub|splash\w*)\b", answer, re.I):
            reasons.append("unrelated_bath_activity")
        if self.topic == "cord_safety" and re.search(r"\b(?:tassels?|break(?:s)? apart|eliminat\w*|guarantee\w*)\b", answer, re.I):
            reasons.append("unsupported_cord_device_assurance")
        if self.topic == "occupied_play" and re.search(r"\b(?:water|basin|glue|tear\w*|scissors|beads?|marbles?)\b", answer, re.I):
            reasons.append("activity_exceeds_available_supervision")
        if self.caregiver_one_handed and re.search(r"\b(?:you|caregiver|parent)\b[^.!?\n]{0,75}\bboth hands\b", answer, re.I):
            reasons.append("conflicting_caregiver_hand_constraint")
        if self.topic == "food_flavours" and re.search(
            r"\b(?:immature|underdeveloped)\s+digestive|\bdigestive system\b[^.!?\n]{0,50}\b(?:matur\w*|develop\w*)\b|"
            r"\b(?:avoid|never (?:give|offer))\s+all\s+(?:spices|seasonings)\b", answer, re.I,
        ):
            reasons.append("unsupported_food_flavour_restriction")
        if self.topic == "food_flavours" and re.search(
            r"\b(?:once|twice|thrice)\s+(?:a|per|each)\s+(?:day|meal)\b|"
            r"\b(?:mid-morning|early afternoon|before bedtime|pinch(?:es)?|spoonfuls?)\b", answer, re.I,
        ):
            reasons.append("unsupported_food_flavour_schedule")
        if self.topic == "feeding":
            if not self.allow_schedule and MEAL_SCHEDULE.search(answer):
                reasons.append("unrequested_feeding_schedule")
            if not self.allow_amount and FOOD_AMOUNT.search(answer):
                reasons.append("unrequested_feeding_amount")
            if self.food_ideas and OFF_TOPIC_ACTIVITY.search(answer):
                reasons.append("unrequested_interaction_activity")
            if self.milk_only and positive_match(EARLY_SOLIDS, answer):
                reasons.append("early_solid_or_water_advice")
            if (self.first_solids
                    and not re.search(r"\b(?:if|when|once|already)\b[^.!?\n]{0,90}\b(?:ready|readiness|steady|solids)\b", answer, re.I)):
                reasons.append("missing_first_food_readiness")
        if self.topic in HEALTH_TOPICS:
            if positive_match(TREATMENT_PRODUCT, answer):
                reasons.append("treatment_product_selection")
            if CARE_DURATION.search(answer):
                reasons.append("unsupported_care_duration")
            if not REFERRAL.search(answer):
                reasons.append("missing_assessment_boundary")
        if self.topic == "cradle_cap" and positive_match(re.compile(
            r"\b(?:apply|use|try|massage|rub)\b[^.!?\n]{0,55}\b(?:oil|oils)\b", re.I), answer):
            reasons.append("individual_scalp_product_selection")
        if self.topic == "cough_cold":
            nasal = re.compile(r"\b(?:use|using|give|giving|put|putting)\b[^.!?\n]{0,70}\b(?:saline|nasal drops|nose drops)\b", re.I)
            for match in nasal.finditer(answer):
                prefix = answer[max(0, match.start() - 120):match.start()]
                professional_first = re.search(r"\b(?:pharmacist|clinician|health professional)\b[^.!?\n]{0,80}\bbefore\s*$", prefix, re.I)
                negated = re.search(r"\b(?:do not|don't|never|avoid|not)\s*$", prefix, re.I)
                if not professional_first and not negated:
                    reasons.append("individual_nasal_product_instruction")
                    break
        if self.topic == "nappy_rash" and not re.search(r"\b(?:fever|high temperature)\b", answer, re.I):
            reasons.append("missing_rash_fever_boundary")
        if self.topic in {"reflux", "cough_cold"} and positive_match(FEED_CHANGE, answer):
            reasons.append("individual_feeding_change")
        if self.topic == "sleep" and not self.allow_timing and CARE_DURATION.search(answer):
            reasons.append("unrequested_sleep_timing")
        if self.infant and self.topic == "sleep" and re.search(r"\b(?:heating pad|hot[ -]water bottle|warm water bottle|electric blanket)\b", answer, re.I):
            reasons.append("sleep_surface_heating_instruction")
        if self.topic == "teething_illness" and re.search(r"\b(?:drool\w*|saliva)\b[^.!?\n]{0,65}\b(?:digesti\w*|diarrh\w*|loose stools)\b|\bteething (?:can |may |sometimes )?(?:cause|affect|lead to)\b", answer, re.I):
            reasons.append("unsupported_teething_explanation")
        if self.infant and self.topic in {"reflux", "sleep"} and not SAFE_SLEEP.search(answer):
            reasons.append("missing_sleep_position_precaution")
        if self.infant and self.topic in {"reflux", "sleep"} and positive_match(UNSAFE_SLEEP, answer):
            reasons.append("unsafe_sleep_position_advice")
        return tuple(reasons)


def get_care_guidance(question: str, age_months: float, context: list[dict] | None = None) -> CareGuidance | None:
    if not isfinite(age_months) or not 0 <= age_months <= 24:
        return None
    request = caregiver_request(question, context or [])
    text = request if question == request else request + " " + question
    # A denied symptom cannot establish the topic for a basic-care shortcut.
    # This only selects references; independent input triage still runs first.
    matched = [
        topic for topic, pattern in TOPICS.items()
        if any(topic not in HEALTH_TOPICS or not _DENIED_SYMPTOM_PREFIX.search(
            text[max(0, match.start() - 120):match.start()],
        ) for match in re.finditer(pattern, text, re.I))
    ]
    # Feeding is often mentioned in reflux or sleep reports; it must not replace
    # the concern. Multiple distinct concerns stay with the general care pipeline.
    concerns = [topic for topic in matched if topic in HEALTH_TOPICS]
    if "teething_illness" in concerns:
        concerns = ["teething_illness"]
    if len(concerns) > 1:
        return None
    topic = concerns[0] if concerns else "food_flavours" if "food_flavours" in matched else "sleep" if "sleep" in matched else next((topic for topic in reversed(TOPICS) if topic in matched), None)
    if (topic in {"sleep", "soothing"}
            and re.search(r"\b(?:games?|activities|play|stories|books?|songs?)\b", text, re.I)):
        # A background care word cannot establish that this basic-care pack
        # answers the requested activity. Let semantic retrieval select support;
        # input triage still runs first, independently of this source shortcut.
        return None
    food_ideas = bool(FOOD_IDEAS.search(text))
    if re.search(r"\b(?:for myself|for me|what (?:should|can) i (?:eat|drink)|my (?:sleep|insomnia))\b|\bi (?:cannot|can't|am not|don't) sleep\b|\bi have (?:a )?(?:reflux|heartburn|rash)\b", text, re.I):
        return None
    if topic == "food_flavours" and re.search(r"\b(?:eyes?|burn\w*|pain|allerg\w*|reaction|irritat\w*|chok\w*)\b", text, re.I):
        return None
    if topic == "feeding" and re.search(r"\b(?:pretend|teddy|doll|toy food|toy kitchen)\b", text, re.I):
        return None
    if topic == "soothing" and re.search(r"\b(?:when|whenever|while|during|after|every time|each time)\b", text, re.I):
        # A specific trigger needs its own references, not only generic comfort advice.
        return None
    if topic == "feeding":
        # These selections cover simple food ideas and feeding statements, not
        # specialist diets, bottle preparation or individual feeding problems.
        if re.search(r"\b(?:allerg\w*|intoleran\w*|diabet\w*|tube|latch\w*|sterili[sz]\w*|dilut\w*|prepare formula|mix formula)\b", text, re.I):
            return None
        if not (food_ideas or SCHEDULE_REQUEST.search(text) or AMOUNT_REQUEST.search(text)
                or re.fullmatch(r"(?:i am|i'm|we are|we're) feeding (?:my|our|the) (?:baby|child|toddler)[.!]?", request.strip(), re.I)):
            return None
    if question != request and (SCHEDULE_REQUEST.search(question) or AMOUNT_REQUEST.search(question)):
        food_ideas = False
    if topic is None or topic == "feeding" and INTERACTION.search(text) and not food_ideas:
        return None
    food_ideas = food_ideas and not INTERACTION.search(text)
    data = load_references()
    entry = next((entry for entry in data["entries"] if entry["topic"] == topic
                  and entry["min_months"] <= age_months < entry["max_months_exclusive"]), None)
    if entry is None:
        return None
    references = []
    for item in entry["references"]:
        source = data["sources"][item["source"]]
        references.append(RetrievedPassage(
            passage_id=f"basic-care-{entry['id']}-{item['source']}", text=item["text"], title=item["section"],
            source_title=f"{source['publisher']}: {source['title']}", source_url=source["url"], pdf_page=item.get("pdf_page"),
            score=0.0, source_age_label=f"{entry['min_months']}-{entry['max_months_exclusive']} months (upper bound excluded)",
            routines=[], selection_method="source_checked_basic_care",
        ))
    return CareGuidance(topic, references, food_ideas, bool(SCHEDULE_REQUEST.search(text)),
                        bool(AMOUNT_REQUEST.search(text)), age_months < 12,
                        6 <= age_months < 7 and not re.search(r"\b(?:already (?:eating )?solids|(?:introduced|started) (?:solid foods|solids))\b", text, re.I),
                        age_months < 6, bool(TIMING_REQUEST.search(text)),
                        bool(re.search(r"\b(?:overnight|night before)\b", text, re.I)),
                        bool(re.search(r"\b(?:one[ -]hand(?:ed)?|one hand free)\b", text, re.I)))


def select_care_references(question: str, age_months: float, context: list[dict],
                           retrieved: list[RetrievedPassage]) -> list[RetrievedPassage]:
    guidance = get_care_guidance(question, age_months, context)
    return guidance.references if guidance else retrieved
