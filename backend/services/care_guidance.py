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
    "reflux": r"\b(?:reflux|regurgitat\w*|spit(?:s|ting)? up|spitting)\b|\b(?:milk|feeds?)\b.{0,45}\b(?:comes? back|coming back|back up|brought up)\b|\bbring(?:s|ing)? up\b.{0,25}\bmilk\b",
    "nappy_rash": r"\b(?:nappy|diaper)[ -]?(?:area )?(?:rash|soreness|irritation)\b|\b(?:bottom|nappy area|diaper area)\b.{0,30}\b(?:sore|red|irritated)\b|\b(?:sore|red|irritated)\b.{0,55}\b(?:bottom|nappy area|diaper area)\b",
    "sleep": r"\b(?:sleep|sleeping|bedtime|night waking)\b|\bwake[sn]?\b.{0,25}\b(?:night|often)\b|\bwaking\b.{0,25}\bnight\b|\bsettle\b.{0,30}\bnight\b",
    "feeding": r"\b(?:food|foods|meals?|feeding|breastfeed\w*|formula|mealtime|recipes?)\b",
}
INTERACTION = re.compile(r"\b(?:talk|talking|communicat\w*|language|sing|singing|bond|bonding|pretend|teddy|doll)\b", re.I)
FOOD_IDEAS = re.compile(r"\b(?:(?:what|which) (?:(?:soft|first|finger|family|healthy) )?foods?|meal ideas?|food ideas?|recipes?|cook|cooking|prepare|make for|serve)\b", re.I)
SCHEDULE_REQUEST = re.compile(r"\b(?:how often|how many (?:times|meals|feeds|snacks)|schedule|timetable|frequency|times (?:a|per) day)\b", re.I)
AMOUNT_REQUEST = re.compile(r"\b(?:how much|amounts?|quantity|quantities|portion|serving size|recipes?|ingredients?)\b", re.I)
TIMING_REQUEST = re.compile(r"\b(?:how long|how much sleep|how many hours|what time|when should|schedule|timetable|minutes?|hours?)\b", re.I)
NUMBER = r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|half|quarter|twice|thrice)"
MEAL_SCHEDULE = re.compile(rf"\b{NUMBER}(?:\s+to\s+{NUMBER})?\s+(?:(?:small|main|regular|nutritious)\s+)?(?:meals?|feeds?|snacks?|eating occasions|times\s+(?:a|per)\s+day)\b|\b(?:twice|thrice) (?:a|per) day\b", re.I)
FOOD_AMOUNT = re.compile(rf"\b{NUMBER}(?:\s+to\s+{NUMBER})?\s+(?:a\s+)?(?:table\s?spoons?|tea\s?spoons?|spoonfuls?|cups?|grams?)\b", re.I)
TREATMENT_PRODUCT = re.compile(r"\b(?:apply(?:ing)?|us(?:e|ing)|try(?:ing)?|spread(?:ing)?|put(?:ting)?|recommend(?:ing)?|giv(?:e|ing)|add(?:ing)?|switch(?:ing)?)\b[^.!?\n]{0,90}\b(?:zinc oxide|hydrocortisone|steroids?|antifungals?|antibiotics?|medicated|creams?|ointments?|lotions?|thickeners?|thickened formula|anti[- ]reflux formula|hypoallergenic formula|probiotics?|gripe water)\b", re.I)
FEED_CHANGE = re.compile(r"\b(?:smaller (?:amounts|feeds)|more (?:often|frequently)|(?:reduce|reducing)\b[^.!?\n]{0,35}\b(?:feed|milk))\b", re.I)
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
        if (url.scheme != "https" or url.hostname not in {"www.nhs.uk", "www.unicef.org"}
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
        if self.topic in {"reflux", "nappy_rash"}:
            rules.append("Give basic care and conditional assessment advice. Do not select creams, active ingredients or treatment durations.")
        if self.topic == "reflux":
            rules.append("Do not change feed amounts or frequency; individual feeding changes need professional advice.")
        if self.topic == "nappy_rash":
            rules.append("Include assessment for rash with fever, worsening or persistent symptoms; do not assume fever is present.")
        if self.topic == "sleep" and not self.allow_timing:
            rules.append("Do not add sleep-hour targets or timed bedtime steps: none were requested.")
        if self.infant and self.topic in {"reflux", "sleep"}:
            rules.append("Keep the distinction between upright awake care and sleeping flat on the back.")
        return "\n".join(rules)

    def findings(self, answer: str) -> tuple[str, ...]:
        reasons = []
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
        if self.topic in {"reflux", "nappy_rash"}:
            if positive_match(TREATMENT_PRODUCT, answer):
                reasons.append("treatment_product_selection")
            if CARE_DURATION.search(answer):
                reasons.append("unsupported_care_duration")
            if not REFERRAL.search(answer):
                reasons.append("missing_assessment_boundary")
        if self.topic == "nappy_rash" and not re.search(r"\b(?:fever|high temperature)\b", answer, re.I):
            reasons.append("missing_rash_fever_boundary")
        if self.topic == "reflux" and positive_match(FEED_CHANGE, answer):
            reasons.append("individual_feeding_change")
        if self.topic == "sleep" and not self.allow_timing and CARE_DURATION.search(answer):
            reasons.append("unrequested_sleep_timing")
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
    matched = [topic for topic, pattern in TOPICS.items() if re.search(pattern, text, re.I)]
    # Feeding is often mentioned in reflux or sleep reports; it must not replace
    # the concern. Multiple distinct concerns stay with the general care pipeline.
    concerns = [topic for topic in matched if topic in {"reflux", "nappy_rash"}]
    if len(concerns) > 1:
        return None
    topic = concerns[0] if concerns else "sleep" if "sleep" in matched else "feeding" if matched else None
    food_ideas = bool(FOOD_IDEAS.search(text))
    if re.search(r"\b(?:for myself|for me|what (?:should|can) i (?:eat|drink)|my (?:sleep|insomnia))\b|\bi (?:cannot|can't|am not|don't) sleep\b|\bi have (?:a )?(?:reflux|heartburn|rash)\b", text, re.I):
        return None
    if topic == "feeding" and re.search(r"\b(?:pretend|teddy|doll|toy food|toy kitchen)\b", text, re.I):
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
            source_title=f"{source['publisher']}: {source['title']}", source_url=source["url"], pdf_page=None,
            score=0.0, source_age_label=f"{entry['min_months']}-{entry['max_months_exclusive']} months (upper bound excluded)",
            routines=[], selection_method="source_checked_basic_care",
        ))
    return CareGuidance(topic, references, food_ideas, bool(SCHEDULE_REQUEST.search(text)),
                        bool(AMOUNT_REQUEST.search(text)), age_months < 12,
                        6 <= age_months < 7 and not re.search(r"\b(?:already (?:eating )?solids|(?:introduced|started) (?:solid foods|solids))\b", text, re.I),
                        age_months < 6, bool(TIMING_REQUEST.search(text)))


def select_care_references(question: str, age_months: float, context: list[dict],
                           retrieved: list[RetrievedPassage]) -> list[RetrievedPassage]:
    guidance = get_care_guidance(question, age_months, context)
    return guidance.references if guidance else retrieved
