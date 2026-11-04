# gives endpoints shared services created at startup or on demand.
from fastapi import HTTPException, Request

from backend.services.retrieval import RetrievalService
from backend.services.speech import SpeechService
from backend.services.caregiver_data import CaregiverDataService
from backend.services.coaching import CoachingService


def get_speech_service(request: Request) -> SpeechService:
    # retrieve the existing model instead of loading a new one for each request.
    service = getattr(request.app.state, "speech_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Speech service is unavailable.")
    return service


def get_retrieval_service(request: Request) -> RetrievalService:
    service = getattr(request.app.state, "retrieval_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Guidance is unavailable. Please try again.")
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
        raise HTTPException(status_code=503, detail="Guidance is unavailable. Please try again.")
    return service
