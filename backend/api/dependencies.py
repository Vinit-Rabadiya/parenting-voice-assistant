# gives endpoints shared services created at startup or on demand.
from fastapi import HTTPException, Request

from backend.services.retrieval import RetrievalService
from backend.services.speech import SpeechService


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


