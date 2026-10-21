"""Bounded per-account counters shared across server processes through Firestore."""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil, isfinite
import time

from firebase_admin import firestore

DAY_OFFSET_SECONDS = 3 * 60 * 60


@dataclass(frozen=True)
class UsageDecision:
    allowed: bool
    retry_after: int = 0
    window: str | None = None


def current_usage(record: dict, now: float) -> dict:
    """Normalize expired windows without writing or consuming an allowance."""
    if type(now) not in (int, float) or not isfinite(now) or now < 0:
        raise ValueError("Usage time must be a finite non-negative timestamp.")
    hour = int(now // 3600)
    day = int((now + DAY_OFFSET_SECONDS) // 86400)

    def count(bucket: str, current: int) -> int:
        stored_bucket = record.get(f"{bucket}_bucket")
        stored_count = record.get(f"{bucket}_count")
        if stored_bucket is None and not record:
            return 0
        if type(stored_bucket) is not int or type(stored_count) is not int or stored_count < 0:
            raise ValueError("Invalid usage counter.")
        if stored_bucket > current:
            raise ValueError("Usage counter is ahead of the current clock.")
        return stored_count if stored_bucket == current else 0

    return {"hour_bucket": hour, "hour_count": count("hour", hour),
            "day_bucket": day, "day_count": count("day", day)}


def next_usage(record: dict, now: float, hourly_limit: int, daily_limit: int) -> tuple[UsageDecision, dict]:
    """Count accepted attempts in fixed hours and Nairobi calendar days."""
    if (type(hourly_limit) is not int or hourly_limit < 1
            or type(daily_limit) is not int or daily_limit < 1):
        raise ValueError("Usage limits must be positive integers.")
    current = current_usage(record, now)
    hour, day = current["hour_bucket"], current["day_bucket"]
    hourly, daily = current["hour_count"], current["day_count"]
    blocked = []
    if hourly >= hourly_limit:
        blocked.append(((hour + 1) * 3600, "hourly"))
    if daily >= daily_limit:
        blocked.append(((day + 1) * 86400 - DAY_OFFSET_SECONDS, "daily"))
    if blocked:
        reset_at, window = max(blocked)
        return UsageDecision(False, max(1, ceil(reset_at - now)), window), record
    return UsageDecision(True), {"hour_bucket": hour, "hour_count": hourly + 1,
                                 "day_bucket": day, "day_count": daily + 1}


class UsageControlService:
    def __init__(self, client, clock=None):
        self.client = client
        self.clock = clock or time.time

    def read(self, uid: str, limits: dict) -> dict:
        now = self.clock()
        items = []
        for action, (hourly_limit, daily_limit) in limits.items():
            snapshot = self.client.collection("users").document(uid).collection("usage").document(action).get()
            record = (snapshot.to_dict() or {}) if snapshot.exists else {}
            current = current_usage(record, now)
            def window(count, limit, reset):
                return {"used": count, "limit": limit, "remaining": max(0, limit - count),
                        "resets_at": datetime.fromtimestamp(reset, timezone.utc)}
            items.append({"action": action,
                          "hourly": window(current["hour_count"], hourly_limit, (current["hour_bucket"] + 1) * 3600),
                          "daily": window(current["day_count"], daily_limit,
                                          (current["day_bucket"] + 1) * 86400 - DAY_OFFSET_SECONDS)})
        return {"items": items, "as_of": datetime.fromtimestamp(now, timezone.utc)}

    def consume(self, uid: str, action: str, hourly_limit: int, daily_limit: int) -> UsageDecision:
        if action not in {"coaching", "child_creation"}:
            raise ValueError("Unknown usage action.")
        document = self.client.collection("users").document(uid).collection("usage").document(action)

        @firestore.transactional
        def reserve(transaction):
            snapshot = document.get(transaction=transaction)
            record = (snapshot.to_dict() or {}) if snapshot.exists else {}
            decision, updated = next_usage(record, self.clock(), hourly_limit, daily_limit)
            if decision.allowed:
                transaction.set(document, updated)
            return decision

        return reserve(self.client.transaction())
