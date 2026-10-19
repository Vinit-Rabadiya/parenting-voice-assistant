# this file handles the /me endpoint to return the currently logged-in user id.
# it is included in backend/api/v1/router.py and called by frontend/src/services/api.js.
from fastapi import APIRouter, Depends, Response, Request, HTTPException
import time
from firebase_admin import auth
from backend.api.dependencies import get_caregiver_data_service
from backend.services.caregiver_data import CaregiverDataService
from backend.core.security import require_authenticated_user
from backend.schemas.auth import UserResponse

router = APIRouter()


@router.delete("/me", status_code=204)
def delete_account(request: Request, user: dict = Depends(require_authenticated_user), service: CaregiverDataService = Depends(get_caregiver_data_service)):
    signed_in_at = getattr(request.state, "auth_time", 0)
    if not isinstance(signed_in_at, (int, float)) or time.time() - signed_in_at > 300:
        raise HTTPException(status_code=403, detail="For account deletion, sign out and sign in again, then retry within five minutes.")
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
    """Verify bearer token, email verification, and TOTP second-factor status, returning the user UID."""
    response.headers["Cache-Control"] = "no-store"
    return UserResponse(uid=user["uid"])
