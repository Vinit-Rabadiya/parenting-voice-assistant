# this file verifies the firebase login token, email verification, and totp mfa status.
# it is imported in backend/api/v1/endpoints/auth.py as a dependency to protect private routes.
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, exceptions
from requests.exceptions import RequestException
from backend.services.account_security import AccountSecurityService
from backend.core.http_security import timed_request_stage

# read the login token from the request header.
bearer = HTTPBearer(auto_error=False)


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

    # check that firebase issued this token and it is still valid.
    try:
        with timed_request_stage(request, "token_verification"):
            claims = auth.verify_id_token(
                credential.credentials,
                app=request.app.state.firebase,
                check_revoked=True,
            )
    except auth.CertificateFetchError:
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
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired login. Log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except (exceptions.FirebaseError, RequestException):
        # stop if the login check cannot finish.
        raise HTTPException(
            status_code=503,
            detail="Authentication temporarily unavailable.",
        ) from None

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
    return AccountSecurityService(request.app.state.firebase)


def get_account_security_state(request: Request, user: dict = Depends(require_verified_user),
                               service: AccountSecurityService = Depends(get_account_security_service)) -> dict:
    try:
        with timed_request_stage(request, "account_security"):
            state = dict(service.read(user["uid"]))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Account verification required.") from None
    except Exception:
        raise HTTPException(status_code=503, detail="Account security is temporarily unavailable.") from None
    claims = request.state.auth_claims
    request.state.account_role = "administrator" if state.get("feedback_summary_admin") is True else "caregiver"
    # A previously issued role claim cannot outlive the current account permission.
    request.state.feedback_summary_admin = (
        request.state.feedback_summary_admin and state.get("feedback_summary_admin") is True
    )
    state["mfa_required"] = (state["mfa_required"] or claims.get("mfa_required") is True
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
    return user


def require_caregiver_user(request: Request, user: dict = Depends(require_authenticated_user)) -> dict:
    if getattr(request.state, "account_role", None) == "administrator":
        raise HTTPException(status_code=403, detail="Administrator accounts cannot access caregiver features. Use a caregiver account.")
    return user


def require_feedback_summary_admin(
    request: Request, user: dict = Depends(require_authenticated_user),
) -> dict:
    if getattr(request.state, "feedback_summary_admin", False) is not True:
        raise HTTPException(status_code=403, detail="Administrator permission required.")
    return user
