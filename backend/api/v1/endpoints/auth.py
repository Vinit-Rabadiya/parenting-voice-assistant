from fastapi import APIRouter, Depends, Response
from backend.core.security import require_authenticated_user
from backend.schemas.auth import UserResponse

router = APIRouter()


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
