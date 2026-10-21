# gives endpoints shared services created at startup or on demand.
from fastapi import Depends, HTTPException, Request
import logging

from backend.services.retrieval import RetrievalService
from backend.services.speech import SpeechService
from backend.services.caregiver_data import CaregiverDataService
from backend.services.coaching import CoachingService
from backend.services.usage import UsageControlService
from backend.core.config import settings

usage_logger = logging.getLogger("uvicorn.error.usage")


def get_speech_service(request: Request) -> SpeechService:
    # retrieve the existing model instead of loading a new one for each request.
    service = getattr(request.app.state, "speech_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Speech service is unavailable.")
    return service


def get_retrieval_service(request: Request) -> RetrievalService:
    service = getattr(request.app.state, "retrieval_service", None)
    if service is None:
        service = RetrievalService()
        request.app.state.retrieval_service = service
    return service


def get_caregiver_data_service(request: Request) -> CaregiverDataService:
    service = getattr(request.app.state, "caregiver_data_service", None)
    if service is None:
        service = CaregiverDataService()
        request.app.state.caregiver_data_service = service
    return service


def get_coaching_service(request: Request) -> CoachingService:
    service = getattr(request.app.state, "coaching_service", None)
    if service is None:
        service = CoachingService()
        request.app.state.coaching_service = service
    return service


def get_usage_control_service(data: CaregiverDataService = Depends(get_caregiver_data_service)) -> UsageControlService:
    return UsageControlService(data.client)


def usage_limits() -> dict:
    return {
        "coaching": (settings.COACH_HOURLY_LIMIT, settings.COACH_DAILY_LIMIT),
        "child_creation": (settings.CHILD_CREATE_HOURLY_LIMIT, settings.CHILD_CREATE_DAILY_LIMIT),
    }


def enforce_usage_limit(service: UsageControlService, uid: str, action: str) -> None:
    limits = usage_limits()
    try:
        decision = service.consume(uid, action, *limits[action])
    except Exception as exc:
        usage_logger.warning("usage_limit action=%s event=unavailable error_type=%s", action, type(exc).__name__)
        raise HTTPException(status_code=503, detail="Request limits could not be checked. Please try again.") from None
    if not decision.allowed:
        usage_logger.info("usage_limit action=%s event=blocked window=%s retry_after=%s", action, decision.window, decision.retry_after)
        label = "coaching request" if action == "coaching" else "profile creation"
        raise HTTPException(status_code=429,
                            detail=f"You have reached your {decision.window} {label} limit.",
                            headers={"Retry-After": str(decision.retry_after)})


