# this file handles the /me endpoint to return the currently logged-in user id.
# it is included in backend/api/v1/router.py and called by frontend/src/services/api.js.
from fastapi import APIRouter, Depends, Response, Request, HTTPException
import time
from math import isfinite
from firebase_admin import auth
from backend.api.dependencies import get_caregiver_data_service
from backend.services.caregiver_data import CaregiverDataService
from backend.core.security import (require_authenticated_user,
                                   get_account_security_state, get_account_security_service)
from backend.schemas.auth import UserResponse, AccountSecurityResponse
from backend.services.account_security import AccountSecurityService
from backend.api.dependencies import get_usage_control_service, usage_limits
from backend.schemas.usage import UsageResponse
from backend.services.usage import UsageControlService

router = APIRouter()


@router.get("/me/security", response_model=AccountSecurityResponse)
def account_security(response: Response, security: dict = Depends(get_account_security_state)):
    # Available during mandatory-MFA setup; never exposes profiles or chat data.
    response.headers["Cache-Control"] = "no-store"
    return security


@router.post("/me/security/mfa/disable", status_code=204)
def disable_mfa(request: Request, user: dict = Depends(require_authenticated_user),
                service: AccountSecurityService = Depends(get_account_security_service),
                security: dict = Depends(get_account_security_state)):
    if security["mfa_required"]:
        raise HTTPException(status_code=403, detail="MFA is required by security policy and cannot be disabled.")
    require_recent_sign_in(request, "changing MFA")
    try:
        service.disable_mfa(user["uid"])
    except PermissionError:
        raise HTTPException(status_code=403, detail="MFA is required by security policy and cannot be disabled.") from None
    except Exception:
        raise HTTPException(status_code=503, detail="MFA settings could not be updated. Refresh account security before retrying.") from None


@router.get("/me/usage", response_model=UsageResponse)
def account_usage(response: Response, user: dict = Depends(require_authenticated_user),
                  service: UsageControlService = Depends(get_usage_control_service)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return service.read(user["uid"], usage_limits())
    except Exception:
        raise HTTPException(status_code=503, detail="Usage could not be loaded. Please try again.") from None


def require_recent_sign_in(request: Request, action: str) -> None:
    signed_in_at = getattr(request.state, "auth_time", 0)
    if (type(signed_in_at) not in (int, float) or not isfinite(signed_in_at)
            or not 0 <= time.time() - signed_in_at <= 300):
        raise HTTPException(status_code=403, detail=f"For {action}, sign out and sign in again, then retry within five minutes.")


@router.delete("/me/data", status_code=204)
def delete_application_data(request: Request, user: dict = Depends(require_authenticated_user),
                            service: CaregiverDataService = Depends(get_caregiver_data_service)):
    require_recent_sign_in(request, "data deletion")
    try:
        service.delete_account_data(user["uid"])
    except Exception:
        raise HTTPException(status_code=503, detail="Data deletion could not finish. Please retry. Some records may already have been removed.") from None


@router.delete("/me", status_code=204)
def delete_account(request: Request, user: dict = Depends(require_authenticated_user), service: CaregiverDataService = Depends(get_caregiver_data_service)):
    require_recent_sign_in(request, "account deletion")
    # Remove application data first so a storage failure can be retried while login exists.
    try:
        service.delete_account_data(user["uid"])
        auth.delete_user(user["uid"], app=request.app.state.firebase)
    except auth.UserNotFoundError:
        pass
    except Exception:
        raise HTTPException(status_code=503, detail="Account deletion could not finish. Please retry. Some records may already have been removed.") from None


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get Current Authenticated User",
)
def current_user(
    response: Response,
    user: dict = Depends(require_authenticated_user),
):
    """Verify the session, email, and applicable MFA requirements."""
    response.headers["Cache-Control"] = "no-store"
    return UserResponse(uid=user["uid"])
