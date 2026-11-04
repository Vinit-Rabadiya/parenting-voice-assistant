"""Read MFA enrollment and apply account security changes through Identity Platform."""

import json
import time
from threading import Lock

from google.auth.transport.requests import AuthorizedSession

from backend.core.config import settings


class AccountSecurityService:
    def __init__(self, app, *, max_idle_sessions: int = 0):
        self.app = app
        self._max_idle_sessions = max_idle_sessions
        self._sessions = []
        self._lock = Lock()
        self._closed = False

    def close(self) -> None:
        with self._lock:
            self._closed = True
            sessions, self._sessions = self._sessions, []
        for session in sessions:
            session.close()

    def _borrow_session(self):
        # Each session is exclusively borrowed. requests.Session is never shared
        # between simultaneous worker threads; account results are never cached.
        with self._lock:
            if self._closed:
                raise RuntimeError("Account security service is closed.")
            if self._sessions:
                return self._sessions.pop()
            return AuthorizedSession(self.app.credential.get_credential())

    def _return_session(self, session, reusable):
        with self._lock:
            if reusable and not self._closed and len(self._sessions) < self._max_idle_sessions:
                self._sessions.append(session)
                return
        session.close()

    def _post(self, action: str, payload: dict) -> dict:
        # The Python Admin SDK does not expose TOTP enrollment management.
        # Use Google's authenticated administration API, never browser-supplied policy.
        session = self._borrow_session()
        reusable = False
        response = None
        try:
            response = session.post(
                f"https://identitytoolkit.googleapis.com/v1/projects/{self.app.project_id}/accounts:{action}",
                json=payload, timeout=10,
            )
            response.raise_for_status()
            value = response.json()
            reusable = True
            return value
        finally:
            if response is not None:
                response.close()
            self._return_session(session, reusable)

    def read(self, uid: str) -> dict:
        records = self._post("lookup", {"localId": [uid]}).get("users", [])
        if len(records) != 1 or records[0].get("localId") != uid:
            raise RuntimeError("Account security could not be confirmed.")
        account = records[0]
        if account.get("disabled") is True or account.get("emailVerified") is not True:
            raise PermissionError("An enabled account with verified email is required.")
        factors = account.get("mfaInfo", [])
        claims = json.loads(account.get("customAttributes") or "{}")
        if not isinstance(factors, list) or not isinstance(claims, dict):
            raise RuntimeError("Invalid account security configuration.")
        if "mfa_required" in claims and type(claims["mfa_required"]) is not bool:
            raise RuntimeError("Invalid MFA policy.")
        return {
            "mfa_enabled": bool(factors),
            "feedback_summary_admin": claims.get("feedback_summary_admin") is True,
            "mfa_required": (settings.AUTH_REQUIRE_MFA or claims.get("mfa_required") is True
                             or claims.get("feedback_summary_admin") is True),
        }

    def disable_mfa(self, uid: str, *, recovery: bool = False) -> None:
        state = self.read(uid)
        if state["mfa_required"] and not recovery:
            raise PermissionError("MFA is required by security policy and cannot be disabled.")
        # Unenrollment and session invalidation are one provider-side update.
        # Mandatory policy claims remain unchanged, including during recovery.
        self._post("update", {"localId": uid, "mfa": {"enrollments": []},
                              "validSince": str(int(time.time()))})
