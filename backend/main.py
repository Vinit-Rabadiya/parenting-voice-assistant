# this file starts the backend server, connects to firebase, and mounts all api routes.
# it is run by uvicorn (python -m uvicorn backend.main:app) and used by tests in tests/conftest.py.
from contextlib import asynccontextmanager

import firebase_admin
from anyio import CapacityLimiter
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from backend.core.config import settings
from backend.core.firebase import initialize_firebase
from backend.core.http_security import configure_http_security
from backend.api.v1.router import api_router
from backend.services.speech import SpeechService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_deployment()
    # connect to firebase when the server starts.
    app.state.firebase = initialize_firebase()
    try:
        # store one model per server process for api/dependencies.py to provide to requests.
        app.state.speech_service = await run_in_threadpool(SpeechService, settings.STT_MODEL)
        # allow one transcription at a time for this server process.
        app.state.speech_limiter = CapacityLimiter(1)
        # requests are served during yield; the finally block runs when the lifespan exits.
        yield
    finally:
        if hasattr(app.state, "speech_limiter"):
            del app.state.speech_limiter
        if hasattr(app.state, "speech_service"):
            del app.state.speech_service
        # close the local firebase connection when the server stops.
        if hasattr(app.state, "firebase") and app.state.firebase:
            firebase_admin.delete_app(app.state.firebase)


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan,
)
configure_http_security(app, production=settings.APP_ENV == "production", allowed_hosts=settings.ALLOWED_HOSTS)

# connect the api routes to the main app.
app.include_router(api_router)

# also allow accessing the routes under /api/v1.
app.include_router(api_router, prefix="/api/v1")
