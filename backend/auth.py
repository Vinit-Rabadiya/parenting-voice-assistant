from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, exceptions
from requests.exceptions import RequestException

bearer = HTTPBearer(auto_error=False)


def require_authenticated_user(
    request: Request,
    credential: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    if credential is None:
        raise HTTPException(
            status_code=401,
            detail="Login required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = auth.verify_id_token(
            credential.credentials,
            app=request.app.state.firebase,
            check_revoked=True,
        )
    except auth.CertificateFetchError:
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
        raise HTTPException(
            status_code=503,
            detail="Authentication temporarily unavailable.",
        ) from None

    if claims.get("email_verified") is not True:
        raise HTTPException(
            status_code=403,
            detail="Email verification required.",
        )

    firebase_claims = claims.get("firebase", {})

    if firebase_claims.get("tenant") is not None:
        raise HTTPException(
            status_code=403,
            detail="Unsupported authentication tenant.",
        )

    if firebase_claims.get("sign_in_second_factor") != "totp":
        raise HTTPException(
            status_code=403,
            detail="Complete authenticator login first.",
        )

    return {"uid": claims["uid"]}