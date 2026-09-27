from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, exceptions
from requests.exceptions import RequestException

# read the login token from the request header.
bearer = HTTPBearer(auto_error=False)


# check that the user is logged in before running an endpoint.
def require_authenticated_user(
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

    # require the authenticator code to have been used for this login.
    if firebase_claims.get("sign_in_second_factor") != "totp":
        raise HTTPException(
            status_code=403,
            detail="Complete authenticator login first.",
        )

    # return the verified user id.
    return {"uid": claims["uid"]}
