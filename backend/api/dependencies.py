from fastapi import HTTPException, Request

from backend.services.speech import SpeechService


def get_speech_service(request: Request) -> SpeechService:
    service = getattr(request.app.state, "speech_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Speech service is unavailable.")
    return service
