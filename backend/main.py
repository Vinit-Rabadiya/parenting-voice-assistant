from contextlib import asynccontextmanager
import firebase_admin
from fastapi import FastAPI, Depends, Response
from backend.firebase import initialize_firebase
from backend.auth import require_authenticated_user

# run setup when the server starts and cleanup when it stops.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # keep the firebase connection available for login checks.
    app.state.firebase = initialize_firebase()
    try:
        # let the server start handling requests.
        yield
    finally:
        # clean up the local connection without deleting the firebase project.
        firebase_admin.delete_app(app.state.firebase)

app = FastAPI(title="Parenting Voice Assistant API", lifespan=lifespan)

# show that the server is running; this address does not require login.
@app.get("/health/live")
def health():
    return {"status":"ok"}

# run the login check before returning the user's id.
@app.get("/me")
def current_user(
    response: Response,
    user: dict = Depends(require_authenticated_user),
):
    # tell browsers and other servers not to keep a saved copy of this response.
    response.headers["Cache-Control"] = "no-store"
    return user
