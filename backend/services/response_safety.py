"""Limited output guardrails, not clinical validation or semantic fact checking."""

from dataclasses import dataclass, replace
from math import isfinite
import re
from typing import TYPE_CHECKING

from backend.services.retrieval import RetrievedPassage
from backend.services.care_guidance import get_care_guidance
from backend.services.conversation_context import caregiver_request

if TYPE_CHECKING:
    from backend.services.coaching import CoachingResult


SAFE_RESPONSE = (
    "I couldn't provide suitable developmental coaching for this request. "
    "For medical advice, diagnosis or treatment, contact a qualified health professional."
)

# Keep detection rules explicit and reviewable. They cover common forms only;
# passing them does not prove an answer is medically safe or evidence-supported.
DOSE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|micrograms?|milligrams?|ml|millilitres?|milliliters?|tablets?|drops?)\b", re.I)
INSTRUCTION_VERB = r"\b(?:give|administer|take|use|start|stop|increase|reduce)\b"
MEDICATION = re.compile(
    INSTRUCTION_VERB
    # Stop before a second instruction verb. Otherwise a negated first clause
    # could hide a positive instruction later in the same sentence.
    + rf"(?:(?!{INSTRUCTION_VERB})[^.!?\n]){{0,80}}?"
    r"\b(?:medicin\w*|medication\w*|drug\w*|antibiotic\w*|paracetamol|acetaminophen|ibuprofen|aspirin|amoxicillin)\b",
    re.I,
)
DIAGNOSIS = re.compile(
    r"\b(?:your\s+(?:baby|child|infant)\s+(?:has|have|is suffering from)|"
    r"this\s+is\s+(?:definitely|certainly))\s+"
    r"(?:autism|pneumonia|malaria|meningitis|an?\s+infection|adhd)\b", re.I,
)
AGE_CLAIM = re.compile(
    r"\byour\s+(?:baby|child|infant)\s+is\s+(\d+(?:\.\d+)?)\s*"
    r"(?:[- ]?months?[- ]?old|years?[- ]?old)\b", re.I,
)
NUMBERED_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
WEB_LINK = re.compile(r"https?://|www\.", re.I)
BLANKET_REASSURANCE = re.compile(
    r"\b(?:completely normal|perfectly normal|nothing to worry about)\b", re.I,
)
CHILD_VIOLENCE = re.compile(r"\b(?:shake|hit|slap)\s+(?:your|the)\s+(?:baby|child|infant)\b", re.I)
UNDERCOOKED_EGG = re.compile(r"\b(?:raw|runny|soft[ -]boiled|lightly[ -]cooked)\s+(?:hen(?:s['\u2019])?\s+)?eggs?\b", re.I)
UNSUITABLE_PLAY_MATERIAL = re.compile(
    r"\b(?:offer\w*|giv\w*|bring\w*|provid\w*|fill\w*|us(?:e|ing))\b[^.!?\n]{0,110}"
    r"\b(?P<material>stones?|pebbles?|plastic bags?|zip[ -]?lock bags?|paper bags?)\b", re.I,
)


def directly_negated(answer, match):
    return bool(re.search(r"\b(?:do not|don['\u2019]t|never)\s*$",
                          answer[max(0, match.start() - 25):match.start()], re.I))


@dataclass(frozen=True)
class SafetyDecision:
    blocked: bool
    reasons: tuple[str, ...]
    replaced_with_basic_care: bool = False


def inspect_response(answer: str, returned_passages: list[RetrievedPassage],
                     evidence: list[RetrievedPassage], child_age_months: float) -> SafetyDecision:
    """Check known output patterns and provenance before persistence or delivery."""
    reasons = []
    if not answer.strip():
        reasons.append("empty_answer")
    if DOSE.search(answer):
        reasons.append("dose_expression")
    # Only a directly attached negation exempts an instruction. This does not
    # exempt an entire paragraph that might also contain an unsafe instruction.
    if any(not directly_negated(answer, m) for m in MEDICATION.finditer(answer)):
        reasons.append("medication_instruction")
    if any(not directly_negated(answer, m) for m in CHILD_VIOLENCE.finditer(answer)):
        reasons.append("harmful_child_instruction")
    # Observed meal suggestion; this narrow rule is not comprehensive food-safety validation.
    if any(not re.search(r"\b(?:avoid|never|do not|don['\u2019]t|not|rather than|instead of)(?:\s+\w+){0,3}\s*$",
                         answer[max(0, m.start() - 45):m.start()], re.I)
           for m in UNDERCOOKED_EGG.finditer(answer)):
        reasons.append("undercooked_egg_suggestion")
    if DIAGNOSIS.search(answer):
        reasons.append("diagnostic_claim")
    # Deliberately narrow: this catches observed wording, not all unsafe reassurance.
    if BLANKET_REASSURANCE.search(answer):
        reasons.append("blanket_reassurance")

    # Compare complete records, not just IDs: a real ID with a changed URL/text
    # must not turn into a trusted source card.
    approved = {passage.passage_id: passage for passage in evidence}
    if any(approved.get(p.passage_id) != p for p in returned_passages):
        reasons.append("invalid_source_provenance")
    returned_ids = {passage.passage_id for passage in returned_passages}
    if any(not 1 <= int(marker) <= len(evidence)
           or evidence[int(marker) - 1].passage_id not in returned_ids
           for group in NUMBERED_CITATION.findall(answer) for marker in group.split(",")):
        reasons.append("invalid_citation_marker")
    # Source links belong in backend-created source cards, not model-generated text.
    if WEB_LINK.search(answer):
        reasons.append("model_generated_link")
    if not isfinite(child_age_months) or child_age_months < 0:
        reasons.append("invalid_child_age")
    elif child_age_months > 24:
        reasons.append("profile_out_of_scope")
    for match in AGE_CLAIM.finditer(answer):
        stated_age = float(match.group(1))
        if "year" in match.group(0).lower():
            stated_age *= 12
        if stated_age > 24 or abs(stated_age - child_age_months) > 1:
            reasons.append("conflicting_age_claim")
            break
    return SafetyDecision(blocked=bool(reasons), reasons=tuple(reasons))


def review_coaching_result(result: "CoachingResult", evidence: list[RetrievedPassage],
                           child_age_months: float, question: str,
                           context: list[dict] | None = None) -> tuple["CoachingResult", SafetyDecision]:
    """Review once, replacing a failed care answer only with permitted source text."""
    # A source fallback must never circumvent a provider safety refusal.
    if result.blocked:
        return result, SafetyDecision(True, ("provider_content_block",))
    decision = inspect_response(result.answer, result.passages, evidence, child_age_months)
    request = caregiver_request(question, context or [])
    if (re.search(r"\b(?:play|games?|sensory|textures?|screen-free|toys?)\b", request, re.I)
            and any(not re.search(r"\b(?:avoid|never|do not|don['\u2019]t|not)(?:\s+\w+){0,2}\s*$",
                                  result.answer[max(0, m.start() - 35):m.start()], re.I)
                    and not re.search(r"\b(?:without|instead of|rather than|not|no|avoid)(?:\s+\w+){0,2}\s*$",
                                      result.answer[m.start():m.start("material")], re.I)
                    for m in UNSUITABLE_PLAY_MATERIAL.finditer(result.answer))):
        decision = SafetyDecision(True, decision.reasons + ("unsuitable_child_play_material",))
    guidance = get_care_guidance(question, child_age_months, context)
    if guidance is None or not all(reference in evidence for reference in guidance.references):
        return result, decision
    findings = guidance.findings(result.answer)
    if not findings and not decision.blocked:
        return result, decision
    replacement = replace(result, answer=guidance.fallback, passages=guidance.references,
                          answer_basis="reference_assisted")
    replacement_check = inspect_response(replacement.answer, replacement.passages, evidence, child_age_months)
    if replacement_check.blocked:
        return result, SafetyDecision(True, decision.reasons + findings + replacement_check.reasons)
    return replacement, SafetyDecision(False, decision.reasons + findings, replaced_with_basic_care=True)
