from contextlib import asynccontextmanager
import firebase_admin
from fastapi import FastAPI, Depends, Response
from backend.firebase import initialize_firebase
from backend.auth import require_authenticated_user

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.firebase = initialize_firebase()
    try:
        yield
    finally:
        firebase_admin.delete_app(app.state.firebase)

app = FastAPI(title="Parenting Voice Assistant API", lifespan=lifespan)

@app.get("/health/live")
def health():
    return {"status":"ok"}

@app.get("/me")
def current_user(
    response: Response,
    user: dict = Depends(require_authenticated_user),
):
    response.headers["Cache-Control"] = "no-store"
    return user
