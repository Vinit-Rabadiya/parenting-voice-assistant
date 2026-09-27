from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, exceptions
from requests.exceptions import RequestException

# read the login token from the request header.
bearer = HTTPBearer(auto_error=False)


# check login before allowing a request to reach a private endpoint.
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

    # check that firebase issued this token and the account is still allowed to use it.
    try:
        claims = auth.verify_id_token(
            credential.credentials,
            app=request.app.state.firebase,
            check_revoked=True,
        )
    except auth.CertificateFetchError:
        # firebase's checking keys could not be fetched, so ask the user to try later.
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
        # refuse access if the login check cannot finish.
        raise HTTPException(
            status_code=503,
            detail="Authentication temporarily unavailable.",
        ) from None

    # a signed-in user must also have a verified email.
    if claims.get("email_verified") is not True:
        raise HTTPException(
            status_code=403,
            detail="Email verification required.",
        )

    firebase_claims = claims.get("firebase", {})

    # reject accounts from separate user groups that this app does not support.
    if firebase_claims.get("tenant") is not None:
        raise HTTPException(
            status_code=403,
            detail="Unsupported authentication tenant.",
        )

    # require an authenticator code to have been used for this login.
    if firebase_claims.get("sign_in_second_factor") != "totp":
        raise HTTPException(
            status_code=403,
            detail="Complete authenticator login first.",
        )

    # return the checked user id; data requests must also check who owns each record.
    return {"uid": claims["uid"]}
