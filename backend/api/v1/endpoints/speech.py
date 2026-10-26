# receives browser wav requests, calls the speech service, and returns transcript json.
# api/v1/router.py registers this endpoint; frontend services/transcription.js calls it.
from anyio import WouldBlock
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from backend.api.dependencies import get_speech_service
from backend.core.security import require_caregiver_user
from backend.api.consent import require_processing_consent
from backend.schemas.speech import TranscriptionResponse
from backend.services.speech import SpeechService
from backend.services.speech_errors import InvalidAudioError, SpeechServiceError


# allow 30 seconds of audio plus space for the wav header.
MAX_AUDIO_BYTES = 16000 * 1 * 2 * 30 + 4096

# run the login dependency before any endpoint registered on this router.
router = APIRouter(
    prefix="/speech",
    dependencies=[Depends(require_caregiver_user)],
)


@router.post("/transcribe", response_model=TranscriptionResponse, dependencies=[Depends(require_processing_consent)])
async def transcribe_audio(
    request: Request,
    service: SpeechService = Depends(get_speech_service),
) -> TranscriptionResponse:
    """receive recorded audio and return its transcript."""
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()

    if content_type != "audio/wav":
        raise HTTPException(
            status_code=415,
            detail="Content-Type must be audio/wav.",
        )
    # collect audio while keeping the request size bounded.
    audio_data = bytearray()

    async for chunk in request.stream():
        if len(audio_data) + len(chunk) > MAX_AUDIO_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Audio recording is too large.",
            )
        audio_data.extend(chunk)

    audio_bytes = bytes(audio_data)

    # reject extra inference requests immediately instead of building a waiting queue.
    limiter = request.app.state.speech_limiter

    try:
        limiter.acquire_nowait()
    except WouldBlock:
        raise HTTPException(
            status_code=429,
            detail="Speech service is busy. Please try again shortly.",
            headers={"Retry-After": "2"},
        ) from None

    try:
        # run blocking transcription outside the event loop.
        return await run_in_threadpool(service.transcribe, audio_bytes)
    except InvalidAudioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SpeechServiceError as exc:
        raise HTTPException(
            status_code=503,
            detail="Speech recognition is unavailable. Please try again.",
        ) from exc
    finally:
        # allow another request after processing succeeds or fails.
        limiter.release()
