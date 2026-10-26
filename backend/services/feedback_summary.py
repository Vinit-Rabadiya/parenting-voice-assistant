"""Count saved answer feedback without exposing private conversation fields."""
from datetime import datetime, timezone
import time

from backend.core.privacy import CONSENT_VERSION
from backend.schemas.admin import FeedbackBucket, FeedbackComment, FeedbackSummary

MAX_DOCUMENTS_PER_GROUP = 10000
MAX_ACCOUNTS = 500
MAX_SCAN_SECONDS = 10
MAX_COMMENTS = 50
PROJECTED_FIELDS = ("feedback.rating", "feedback.helpful", "feedback.reasons",
                    "feedback.comment", "feedback.recorded_at", "role")
REASONS = {
    "unclear": "Unclear", "repeated_advice": "Repeated advice",
    "did_not_answer": "Did not answer the message",
    "not_age_appropriate": "Not suited to the child's age",
}
RATINGS = {1: "1 — Not helpful", 2: "2 — Slightly helpful", 3: "3 — Somewhat helpful",
           4: "4 — Helpful", 5: "5 — Very helpful"}


def aware_time(value):
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def summarize_feedback(records: list[dict]) -> FeedbackSummary:
    """Count each answer once and include a bounded list of shared comments."""
    def bucket(label, matches):
        return FeedbackBucket(label=label, count=sum(bool(matches(value)) for value in records))

    shared = [value for value in records if value.get("comment")]
    comments = [FeedbackComment(comment=value["comment"], rating=value.get("rating"),
                                helpful=value.get("helpful"),
                                reasons=[REASONS[reason] for reason in value.get("reasons", []) if reason in REASONS])
                for value in shared[:MAX_COMMENTS]]
    return FeedbackSummary(
        ratings=[bucket(label, lambda value, number=number:
                        type(value.get("rating")) is int and value["rating"] == number)
                 for number, label in RATINGS.items()],
        reasons=[bucket(label, lambda value, reason=reason: reason in value.get("reasons", []))
                 for reason, label in REASONS.items()],
        legacy_helpfulness=[bucket(label, lambda value, flag=flag:
                                  value.get("rating") is None and value.get("helpful") is flag)
                            for flag, label in ((True, "Helpful"), (False, "Not helpful"))],
        comments=comments, comment_count=len(shared),
    )


class FeedbackSummaryService:
    def __init__(self, client):
        self.client = client

    def read(self) -> FeedbackSummary:
        records, consent = [], {}
        now = datetime.now(timezone.utc)
        started = time.perf_counter()

        def check_budget():
            if time.perf_counter() - started > MAX_SCAN_SECONDS:
                raise RuntimeError("Aggregate report time budget exceeded.")

        for group in ("messages", "interactions"):
            check_budget()
            query = self.client.collection_group(group).select(PROJECTED_FIELDS).limit(MAX_DOCUMENTS_PER_GROUP + 1)
            for number, snapshot in enumerate(query.stream(timeout=10, retry=None), start=1):
                check_budget()
                # Never present a truncated scan as a complete report.
                if number > MAX_DOCUMENTS_PER_GROUP:
                    raise RuntimeError("Aggregate report scan limit exceeded.")
                path = snapshot.reference.path.split("/")
                valid = (len(path) == 6 and path[0] == "users" and path[2] == "conversations"
                         and path[4] == "messages") if group == "messages" else (
                             len(path) == 4 and path[0] == "users" and path[2] == "interactions")
                if not valid:
                    continue
                data = snapshot.to_dict() or {}
                if group == "messages" and data.get("role") != "assistant":
                    continue
                value = data.get("feedback")
                if not isinstance(value, dict):
                    continue
                recorded = value.get("recorded_at")
                rating, helpful = value.get("rating"), value.get("helpful")
                if (not aware_time(recorded) or recorded > now
                        or not ((type(rating) is int and 1 <= rating <= 5) or type(helpful) is bool)):
                    continue
                uid = path[1]
                if uid not in consent:
                    if len(consent) >= MAX_ACCOUNTS:
                        raise RuntimeError("Aggregate report account limit exceeded.")
                    account = self.client.collection("users").document(uid).get(
                        field_paths=["consent_version", "consent_at", "caregiver_authority"],
                        timeout=5, retry=None,
                    )
                    consent[uid] = (account.to_dict() or {}) if account.exists else {}
                    check_budget()
                accepted = consent[uid]
                if (accepted.get("consent_version") != CONSENT_VERSION
                        or accepted.get("caregiver_authority") is not True
                        or not aware_time(accepted.get("consent_at"))
                        or recorded < accepted["consent_at"]):
                    continue
                # Retain only allowlisted values, even if a storage mock or future
                # backend ignores the Firestore field projection.
                reasons = value.get("reasons", [])
                comment = value.get("comment")
                candidate = {"rating": rating if type(rating) is int and 1 <= rating <= 5 else None,
                             "helpful": helpful if type(helpful) is bool else None,
                             "comment": comment.strip() if isinstance(comment, str) and len(comment) <= 500 else None,
                             "recorded_at": recorded,
                             "reasons": [reason for reason in REASONS if isinstance(reasons, list) and reason in reasons]}
                records.append(candidate)
        check_budget()
        records.sort(key=lambda value: value["recorded_at"], reverse=True)
        return summarize_feedback(records)
