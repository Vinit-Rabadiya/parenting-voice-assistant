# this file starts the backend server, connects to firebase, and mounts all api routes.
# it is run by uvicorn (python -m uvicorn backend.main:app) and used by tests in tests/conftest.py.
from contextlib import asynccontextmanager
import logging

import firebase_admin
from anyio import CancelScope, CapacityLimiter
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from backend.core.config import PROJECT_ROOT, settings
from backend.core.firebase import initialize_firebase
from backend.core.frontend import mount_frontend
from backend.core.http_security import configure_http_security
from backend.api.v1.router import api_router
from backend.services.speech import SpeechService
from backend.services.coaching import CoachingService
from backend.services.retrieval import RetrievalService
from backend.services.account_security import AccountSecurityService

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_deployment()
    settings.validate_coaching()
    # connect to firebase when the server starts.
    app.state.firebase = initialize_firebase()
    try:
        app.state.account_security_service = AccountSecurityService(app.state.firebase, max_idle_sessions=8)
        # Own one wrapper per process; remote clients remain lazy until first use.
        app.state.coaching_service = CoachingService()
        app.state.retrieval_service = RetrievalService()
        # store one model per server process for api/dependencies.py to provide to requests.
        app.state.speech_service = await run_in_threadpool(SpeechService, settings.STT_MODEL)
        # allow one transcription at a time for this server process.
        app.state.speech_limiter = CapacityLimiter(1)
        # requests are served during yield; the finally block runs when the lifespan exits.
        yield
    finally:
        # Finish releasing local resources even if the lifespan was cancelled.
        with CancelScope(shield=True):
            for name in ("retrieval_service", "coaching_service", "account_security_service"):
                service = getattr(app.state, name, None)
                if service is not None:
                    delattr(app.state, name)
                    try:
                        await run_in_threadpool(service.close)
                    except Exception as exc:
                        # One cleanup failure must not leak details or skip other services.
                        logger.warning("service_cleanup service=%s error_type=%s", name, type(exc).__name__)
            if hasattr(app.state, "speech_limiter"):
                del app.state.speech_limiter
            if hasattr(app.state, "speech_service"):
                del app.state.speech_service
            # This wrapper uses Firebase-owned clients; discard it before the app is deleted.
            if hasattr(app.state, "caregiver_data_service"):
                del app.state.caregiver_data_service
            # close the local firebase connection when the server stops.
            if hasattr(app.state, "firebase") and app.state.firebase:
                firebase_app = app.state.firebase
                del app.state.firebase
                firebase_admin.delete_app(firebase_app)


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

if settings.SERVE_FRONTEND:
    mount_frontend(app, api_router, PROJECT_ROOT / "frontend/dist")
