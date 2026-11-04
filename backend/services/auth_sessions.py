"""Bounded reuse of successful remote caregiver security checks, never raw tokens."""
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
import hmac
from math import isfinite
import secrets
from threading import Lock
import time


@dataclass(frozen=True)
class SessionSecurity:
    uid: str
    security: dict
    deadline: float
    token_expiry: float


class AuthSessionCache:
    """Local JWT validation still runs on every request; only remote checks age."""

    def __init__(self, ttl_seconds=60, *, capacity=256, clock=time.monotonic, wall_clock=time.time):
        if type(ttl_seconds) not in (int, float) or not isfinite(ttl_seconds) or not 0 <= ttl_seconds <= 18000:
            raise ValueError("AUTH_SESSION_CACHE_TTL_SECONDS must be between 0 and 18000.")
        if type(capacity) is not int or capacity < 1:
            raise ValueError("Session cache capacity must be a positive integer.")
        self.ttl_seconds = ttl_seconds
        self.capacity = capacity
        self.clock = clock
        self.wall_clock = wall_clock
        self._secret = secrets.token_bytes(32)
        self._entries = OrderedDict()
        self._lock = Lock()
        self._revision = 0
        self._closed = False

    def token_key(self, token: str) -> bytes:
        return hmac.digest(self._secret, token.encode("utf-8"), sha256)

    def get(self, key: bytes) -> SessionSecurity | None:
        with self._lock:
            entry = self._entries.get(key)
            if self._closed or self.ttl_seconds == 0 or entry is None:
                return None
            if self.clock() >= entry.deadline or self.wall_clock() >= entry.token_expiry:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return SessionSecurity(entry.uid, dict(entry.security), entry.deadline, entry.token_expiry)

    def invalidate_user(self, uid: str) -> int:
        """A revision also prevents an in-flight older lookup from repopulating."""
        with self._lock:
            self._revision += 1
            self._entries = OrderedDict((key, entry) for key, entry in self._entries.items() if entry.uid != uid)
            return self._revision

    def discard(self, key: bytes) -> None:
        with self._lock:
            self._entries.pop(key, None)
            self._revision += 1

    def remember(self, key: bytes, claims: dict, security: dict, *, started: float, revision: int) -> None:
        expiry, uid = claims.get("exp"), claims.get("uid")
        if (not isinstance(uid, str) or not uid or type(expiry) not in (int, float)
                or not isfinite(expiry) or claims.get("feedback_summary_admin") is True
                or security.get("feedback_summary_admin") is True):
            return
        # Retain only the fields needed for live MFA/role policy, without profile data.
        state = {name: security.get(name) is True
                 for name in ("mfa_enabled", "mfa_required", "feedback_summary_admin")}
        with self._lock:
            if (self._closed or self.ttl_seconds == 0 or revision != self._revision
                    or self.clock() >= started + self.ttl_seconds or self.wall_clock() >= expiry):
                return
            self._entries[key] = SessionSecurity(uid, state, started + self.ttl_seconds, expiry)
            self._entries.move_to_end(key)
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._revision += 1
            self._entries.clear()
