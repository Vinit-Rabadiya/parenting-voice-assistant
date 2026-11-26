# this file starts the backend server, connects to firebase, and mounts all api routes.
# it is run by uvicorn (python -m uvicorn backend.main:app) and used by tests in tests/conftest.py.
from contextlib import asynccontextmanager
from functools import partial
import logging

import firebase_admin
from anyio import CancelScope, CapacityLimiter, create_task_group, move_on_after, sleep, to_thread
from fastapi import FastAPI
from firebase_admin import firestore
from starlette.concurrency import run_in_threadpool

from backend.core.config import PROJECT_ROOT, settings
from backend.core.firebase import initialize_firebase
from backend.core.frontend import mount_frontend
from backend.core.http_security import configure_http_security
from backend.api.v1.router import api_router
from backend.services.speech import SpeechService
from backend.services.coaching import CoachingService
from backend.services.provider_failover import ProviderFailoverService
from backend.services.retrieval import RetrievalService
from backend.services.account_security import AccountSecurityService
from backend.services.auth_sessions import AuthSessionCache
from backend.services.token_usage import TokenUsageService
from backend.core.request_admission import RequestAdmission

logger = logging.getLogger("uvicorn.error")


async def warm_references(service: RetrievalService) -> None:
    """Optional warmup must not delay serving requests or hold shutdown open."""
    with move_on_after(settings.QDRANT_WARMUP_TIMEOUT_SECONDS):
        try:
            # Cancellation ends this wait; the worker's in-flight network request
            # finishes under its own timeout. Service closure rejects late updates.
            await to_thread.run_sync(partial(
                service.warmup, timeout=settings.QDRANT_WARMUP_TIMEOUT_SECONDS,
                retries=settings.QDRANT_WARMUP_RETRIES,
            ), abandon_on_cancel=True)
        except Exception as exc:
            logger.warning("qdrant_warmup_error: %s", type(exc).__name__)


async def persist_token_usage(service: TokenUsageService) -> None:
    while True:
        await sleep(15)
        await to_thread.run_sync(service.flush)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_deployment()
    settings.validate_coaching()
    # connect to firebase when the server starts.
    app.state.firebase = initialize_firebase()
    try:
        app.state.auth_session_cache = AuthSessionCache(settings.AUTH_SESSION_CACHE_TTL_SECONDS)
        app.state.request_admission = RequestAdmission(enforce_rate=settings.APP_ENV == "production")
        app.state.account_security_service = AccountSecurityService(app.state.firebase, max_idle_sessions=8)
        usage_service = TokenUsageService(lambda: firestore.client(app=app.state.firebase), settings.APP_ENV)
        app.state.token_usage_service = usage_service
        # Own one wrapper per process; remote clients remain lazy until first use.
        service_type = ProviderFailoverService if settings.COACHING_PROVIDER_FAILOVER else CoachingService
        app.state.coaching_service = service_type(usage_recorder=usage_service.record)
        app.state.retrieval_service = RetrievalService()
        app.state.speech_service = await run_in_threadpool(SpeechService, settings.STT_MODEL)
        app.state.speech_limiter = CapacityLimiter(1)
        async with create_task_group() as tasks:
            tasks.start_soon(persist_token_usage, usage_service)
            if settings.QDRANT_WARMUP_ENABLED:
                tasks.start_soon(warm_references, app.state.retrieval_service)
            try:
                yield
            finally:
                tasks.cancel_scope.cancel()
    finally:
        # Finish releasing local resources even if the lifespan was cancelled.
        with CancelScope(shield=True):
            for name in ("request_admission", "auth_session_cache", "retrieval_service", "coaching_service",
                         "token_usage_service", "account_security_service"):
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
configure_http_security(app, production=settings.APP_ENV == "production", allowed_hosts=settings.ALLOWED_HOSTS,
                        firebase_project_id=settings.FIREBASE_PROJECT_ID, auth_origins=settings.CSP_AUTH_ORIGINS,
                        development_timing_directory=PROJECT_ROOT / "tmp" if settings.APP_ENV == "development" else None)

# connect the api routes to the main app.
app.include_router(api_router)

# also allow accessing the routes under /api/v1.
app.include_router(api_router, prefix="/api/v1")

if settings.SERVE_FRONTEND:
    mount_frontend(app, api_router, PROJECT_ROOT / "frontend/dist")
