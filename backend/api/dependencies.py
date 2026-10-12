# gives the speech endpoint the shared service created by backend/main.py at startup.
from fastapi import HTTPException, Request

from backend.services.speech import SpeechService


def get_speech_service(request: Request) -> SpeechService:
    # retrieve the existing model instead of loading a new one for each request.
    service = getattr(request.app.state, "speech_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Speech service is unavailable.")
    return service
