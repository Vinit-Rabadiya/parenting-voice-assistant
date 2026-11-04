"""Release checked sentence prefixes, retaining complete checks for care-specific rules."""
import re

from backend.services.care_guidance import get_care_guidance
from backend.services.coaching import CoachingResult
from backend.services.response_safety import review_coaching_result


class AnswerStreamGuard:
    def __init__(self, question, age, evidence, context, emit):
        self.question, self.age, self.evidence, self.context = question, age, evidence, context
        self.emit = emit
        self.text, self.sent = "", 0
        # These rules can replace an answer for missing conditions. A prefix
        # cannot establish that a complete care answer meets those requirements.
        self.hold = get_care_guidance(question, age, context) is not None
        self._initial_hold = self.hold

    def reset(self):
        self.text, self.sent, self.hold = "", 0, self._initial_hold

    def append(self, delta: str):
        self.text += delta
        if len(self.text) > 16000:
            raise ValueError("Response exceeds the streaming bound.")
        if self.hold:
            return
        boundaries = list(re.finditer(r"[.!?](?:[ \t]+|\n)|\n", self.text[self.sent:]))
        if not boundaries:
            return
        end = self.sent + boundaries[-1].end()
        candidate = self.text[:end]
        reviewed, decision = review_coaching_result(
            CoachingResult(candidate, self.evidence), self.evidence, self.age, self.question, self.context,
        )
        if decision.blocked or decision.replaced_with_basic_care or reviewed.answer != candidate:
            self.hold = True
            return
        self.emit("delta", {"text": candidate[self.sent:]})
        self.sent = end
