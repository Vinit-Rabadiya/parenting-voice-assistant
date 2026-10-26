"""Read MFA enrollment and apply account security changes through Identity Platform."""

import json
import time

from google.auth.transport.requests import AuthorizedSession

from backend.core.config import settings


class AccountSecurityService:
    def __init__(self, app):
        self.app = app

    def _post(self, action: str, payload: dict) -> dict:
        # The Python Admin SDK does not expose TOTP enrollment management.
        # Use Google's authenticated administration API, never browser-supplied policy.
        session = AuthorizedSession(self.app.credential.get_credential())
        try:
            response = session.post(
                f"https://identitytoolkit.googleapis.com/v1/projects/{self.app.project_id}/accounts:{action}",
                json=payload, timeout=10,
            )
            response.raise_for_status()
            return response.json()
        finally:
            session.close()

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
