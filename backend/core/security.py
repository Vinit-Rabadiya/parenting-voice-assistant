# this file verifies the firebase login token, email verification, and totp mfa status.
# it is imported in backend/api/v1/endpoints/auth.py as a dependency to protect private routes.
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, exceptions
from requests.exceptions import RequestException
import re
from backend.services.account_security import AccountSecurityService
from backend.core.http_security import timed_request_stage
from backend.core.config import settings
from backend.core.request_admission import AdmissionRejected

# read the login token from the request header.
bearer = HTTPBearer(auto_error=False)


def can_reuse_session(request: Request) -> bool:
    # Explicit allowlist: new routes, all destructive operations, security and
    # administrator requests default to fresh provider checks.
    path = request.url.path
    for prefix in ("/api/v1", "/api"):
        if path.startswith(prefix + "/"):
            path = path[len(prefix):]
            break
    if request.method == "GET":
        return path in {"/me", "/me/startup", "/children", "/conversations", "/privacy/consent"} or bool(
            re.fullmatch(r"/conversations/[^/]+", path)
        )
    return request.method == "POST" and (path in {"/coach", "/speech/transcribe"} or bool(
        re.fullmatch(r"/coach/[A-Za-z0-9_-]+/feedback", path)
    ))


def invalidate_user_session(request: Request, uid: str) -> None:
    cache = getattr(request.app.state, "auth_session_cache", None)
    if cache is not None:
        cache.invalidate_user(uid)


# check that the user is logged in before running an endpoint.
def require_verified_user(
    request: Request,
    credential: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    if credential is None:
        raise HTTPException(
            status_code=401,
            detail="Login required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    cache = getattr(request.app.state, "auth_session_cache", None)
    reusable = can_reuse_session(request)
    key = cache.token_key(credential.credentials) if cache is not None else None
    cached = cache.get(key) if cache is not None and reusable else None
    request.state.auth_cache_key = key
    request.state.auth_cache_reusable = reusable
    request.state.auth_cache_started = cache.clock() if cache is not None else 0

    # Always verify the JWT signature, issuer/audience and expiry. The Firebase
    # SDK caches public signing certificates. Reuse only a recent successful
    # revocation + account-policy check for this exact token.
    try:
        with timed_request_stage(request, "token_verification"):
            claims = auth.verify_id_token(
                credential.credentials,
                app=request.app.state.firebase,
                check_revoked=cached is None,
            )
            # A certificate refresh can take long enough for the cached check
            # to expire, or another request can invalidate it while we verify.
            if cached is not None:
                cached = cache.get(key)
                if cached is None:
                    claims = auth.verify_id_token(credential.credentials, app=request.app.state.firebase, check_revoked=True)
    except auth.CertificateFetchError:
        if cache is not None:
            cache.discard(key)
        # stop if firebase server keys cannot be reached right now.
        raise HTTPException(
            status_code=503,
            detail="Authentication temporarily unavailable.",
        ) from None
    except (
        auth.InvalidIdTokenError,
        auth.RevokedIdTokenError,
        auth.UserDisabledError,
        auth.UserNotFoundError,
        ValueError,
    ):
        if cache is not None:
            cache.discard(key)
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired login. Log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except (exceptions.FirebaseError, RequestException):
        if cache is not None:
            cache.discard(key)
        # stop if the login check cannot finish.
        raise HTTPException(
            status_code=503,
            detail="Authentication temporarily unavailable.",
        ) from None

    if cached is not None and cached.uid != claims.get("uid"):
        cache.discard(key)
        raise HTTPException(status_code=401, detail="Invalid or expired login. Log in again.",
                            headers={"WWW-Authenticate": "Bearer"})
    request.state.auth_cached_security = cached

    # check that the user confirmed their email.
    if claims.get("email_verified") is not True:
        raise HTTPException(
            status_code=403,
            detail="Email verification required.",
        )

    firebase_claims = claims.get("firebase", {})

    # reject user groups that this app does not support.
    if firebase_claims.get("tenant") is not None:
        raise HTTPException(
            status_code=403,
            detail="Unsupported authentication tenant.",
        )

    # Sensitive endpoints can require a recent sign-in using this verified claim.
    request.state.auth_time = claims.get("auth_time", 0)
    request.state.auth_claims = claims
    # Only a verified server-issued boolean claim grants aggregate-report access.
    request.state.feedback_summary_admin = claims.get("feedback_summary_admin") is True
    # return the verified user id.
    return {"uid": claims["uid"]}


def get_account_security_service(request: Request) -> AccountSecurityService:
    service = getattr(request.app.state, "account_security_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Account security is temporarily unavailable.")
    return service


def get_account_security_state(request: Request, user: dict = Depends(require_verified_user),
                               service: AccountSecurityService = Depends(get_account_security_service)) -> dict:
    cached = getattr(request.state, "auth_cached_security", None)
    if cached is not None:
        state = dict(cached.security)
    else:
        cache = getattr(request.app.state, "auth_session_cache", None)
        if cache is not None:
            request.state.auth_cache_revision = cache.invalidate_user(user["uid"])
        try:
            with timed_request_stage(request, "account_security"):
                state = dict(service.read(user["uid"]))
        except PermissionError:
            raise HTTPException(status_code=403, detail="Account verification required.") from None
        except Exception:
            raise HTTPException(status_code=503, detail="Account security is temporarily unavailable.") from None
    claims = request.state.auth_claims
    request.state.account_role = "administrator" if state.get("feedback_summary_admin") is True else "caregiver"
    # Privileged requests always refresh this permission from the provider.
    request.state.feedback_summary_admin = (
        request.state.feedback_summary_admin and state.get("feedback_summary_admin") is True
    )
    state["mfa_required"] = (state["mfa_required"] or settings.AUTH_REQUIRE_MFA or claims.get("mfa_required") is True
                             or claims.get("feedback_summary_admin") is True)
    return state


def require_authenticated_user(request: Request, user: dict = Depends(require_verified_user),
                               security: dict = Depends(get_account_security_state)) -> dict:
    # An opted-in account still needs its second factor. Old first-factor tokens
    # cannot bypass enrollment, and mandatory policy is checked server-side.
    if security["mfa_required"] and not security["mfa_enabled"]:
        raise HTTPException(status_code=403, detail="MFA is required by security policy. Set up an authenticator in My Account.")
    if security["mfa_enabled"] or security["mfa_required"]:
        if request.state.auth_claims.get("firebase", {}).get("sign_in_second_factor") != "totp":
            detail = ("MFA is required by security policy. Set up or complete authenticator sign-in."
                      if security["mfa_required"] else "Complete authenticator login first.")
            raise HTTPException(status_code=403, detail=detail)
    cache = getattr(request.app.state, "auth_session_cache", None)
    if (cache is not None and getattr(request.state, "auth_cache_reusable", False)
            and getattr(request.state, "auth_cached_security", None) is None
            and hasattr(request.state, "auth_cache_revision")):
        # Only a fully authorized session can be reused; denied first-factor
        # logins, administrators and security-setting reads never populate it.
        cache.remember(request.state.auth_cache_key, request.state.auth_claims, security,
                       started=request.state.auth_cache_started, revision=request.state.auth_cache_revision)
    admission = getattr(request.app.state, "request_admission", None)
    if admission is not None and request.method == "GET":
        try:
            admission.check_read(user["uid"])
        except AdmissionRejected as exc:
            raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "1"}) from None
    return user


def require_caregiver_user(request: Request, user: dict = Depends(require_authenticated_user)) -> dict:
    request.state.caregiver_uid = user["uid"]
    if getattr(request.state, "account_role", None) == "administrator":
        raise HTTPException(status_code=403, detail="Administrator accounts cannot access caregiver features. Use a caregiver account.")
    path = request.url.path.removeprefix("/api/v1").removeprefix("/api")
    admission = getattr(request.app.state, "request_admission", None)
    if (admission is not None and request.method in {"POST", "PATCH", "PUT"}
            and path not in {"/coach", "/speech/transcribe"}):
        try:
            admission.check_write(user["uid"])
        except AdmissionRejected as exc:
            raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "3"}) from None
    return user


def require_feedback_summary_admin(
    request: Request, user: dict = Depends(require_authenticated_user),
) -> dict:
    if getattr(request.state, "feedback_summary_admin", False) is not True:
        raise HTTPException(status_code=403, detail="Administrator permission required.")
    return user
