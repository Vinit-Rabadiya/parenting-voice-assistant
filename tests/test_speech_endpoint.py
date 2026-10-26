import io
import wave
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request

from backend.api.v1.endpoints.speech import MAX_AUDIO_BYTES, transcribe_audio
from backend.schemas.speech import TranscriptionResponse
from backend.services.audio_validation import validate_audio
from backend.services.speech_errors import InvalidAudioError, SpeechServiceError


# provide valid audio without recording a microphone or saving a file.
@pytest.fixture
def wav_audio():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(bytes(16000 * 2))
    return buffer.getvalue()


# replace only token verification so the real email and mfa checks still run.
@pytest.fixture
def token_verifier(monkeypatch):
    verifier = Mock(return_value={
        "uid": "test-caregiver",
        "email_verified": True,
        "firebase": {"sign_in_second_factor": "totp"},
    })
    monkeypatch.setattr("backend.core.security.auth.verify_id_token", verifier)
    return verifier


# add test credentials to the client without signing in to firebase.
@pytest.fixture
def signed_in_client(client, token_verifier):
    client.headers.update({"Authorization": "Bearer test-token"})
    return client


# reuse the fake service installed by the existing application startup fixture.
@pytest.fixture
def speech_service(client):
    service = client.app.state.speech_service
    service.transcribe.return_value = TranscriptionResponse(
        text="My baby is six months old.", audio_seconds=1, processing_seconds=0.25,
    )
    return service


# both public route prefixes must enforce login before calling the service.
@pytest.mark.parametrize("path", ["/speech/transcribe", "/api/v1/speech/transcribe"])
def test_missing_login_is_rejected(client, speech_service, path):
    response = client.post(path, content=b"audio", headers={"Content-Type": "audio/wav"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Login required."
    speech_service.transcribe.assert_not_called()


# invalid tokens must not reach transcription.
def test_invalid_token_is_rejected(signed_in_client, token_verifier, speech_service):
    token_verifier.side_effect = ValueError("invalid token")
    response = signed_in_client.post("/speech/transcribe")
    assert response.status_code == 401
    speech_service.transcribe.assert_not_called()


# valid tokens still need verified email and a completed authenticator login.
@pytest.mark.parametrize("verified, firebase, detail", [
    (False, {"sign_in_second_factor": "totp"}, "Email verification required."),
    (True, {}, "Complete authenticator login first."),
])
def test_incomplete_login_is_rejected(
    signed_in_client, token_verifier, speech_service, verified, firebase, detail,
):
    from backend.core.security import get_account_security_service
    signed_in_client.app.dependency_overrides[get_account_security_service]().read.return_value = {
        "mfa_enabled": True, "mfa_required": False,
    }
    token_verifier.return_value = {
        "uid": "test-caregiver", "email_verified": verified, "firebase": firebase,
    }
    response = signed_in_client.post("/speech/transcribe")
    assert response.status_code == 403
    assert response.json()["detail"] == detail
    speech_service.transcribe.assert_not_called()


# registered endpoints must forward audio and serialize the existing response schema.
@pytest.mark.parametrize("path", ["/speech/transcribe", "/api/v1/speech/transcribe"])
def test_valid_audio_returns_transcript(signed_in_client, speech_service, wav_audio, path):
    response = signed_in_client.post(
        path, content=wav_audio, headers={"Content-Type": "Audio/WAV; charset=binary"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "text": "My baby is six months old.", "audio_seconds": 1.0,
        "processing_seconds": 0.25,
    }
    speech_service.transcribe.assert_called_once_with(wav_audio)
    assert signed_in_client.app.state.speech_limiter.borrowed_tokens == 0


# incorrect or absent content types must be rejected before inference.
@pytest.mark.parametrize("content_type", [None, "application/json", "audio/mpeg"])
def test_unsupported_content_type_is_rejected(signed_in_client, speech_service, content_type):
    headers = {} if content_type is None else {"Content-Type": content_type}
    response = signed_in_client.post("/speech/transcribe", content=b"audio", headers=headers)
    assert response.status_code == 415
    speech_service.transcribe.assert_not_called()


# valid headers cannot bypass the real audio validator.
@pytest.mark.parametrize("audio", [b"", b"not a wav"], ids=["empty", "malformed"])
def test_invalid_audio_returns_422(signed_in_client, speech_service, audio):
    speech_service.transcribe.side_effect = validate_audio
    response = signed_in_client.post(
        "/speech/transcribe", content=audio, headers={"Content-Type": "audio/wav"},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert signed_in_client.app.state.speech_limiter.borrowed_tokens == 0


# reject large bodies before they reach the speech service.
def test_oversized_audio_returns_413(signed_in_client, speech_service):
    response = signed_in_client.post(
        "/speech/transcribe", content=b"x" * (MAX_AUDIO_BYTES + 1),
        headers={"Content-Type": "audio/wav"},
    )
    assert response.status_code == 413
    speech_service.transcribe.assert_not_called()


# check the accumulated size even when there is no content-length header.
@pytest.mark.asyncio
async def test_chunked_body_stops_at_size_limit():
    messages = iter([
        {"type": "http.request", "body": b"x" * MAX_AUDIO_BYTES, "more_body": True},
        {"type": "http.request", "body": b"x", "more_body": True},
    ])
    received = 0

    async def receive():
        nonlocal received
        received += 1
        return next(messages)

    request = Request({
        "type": "http", "headers": [(b"content-type", b"audio/wav")],
    }, receive)
    service = Mock()
    with pytest.raises(HTTPException) as error:
        await transcribe_audio(request, service)
    assert error.value.status_code == 413
    assert received == 2
    service.transcribe.assert_not_called()


# the size boundary passes the byte check but still needs service validation.
def test_exact_size_limit_reaches_service(signed_in_client, speech_service):
    speech_service.transcribe.side_effect = InvalidAudioError("invalid wav")
    response = signed_in_client.post(
        "/speech/transcribe", content=b"x" * MAX_AUDIO_BYTES,
        headers={"Content-Type": "audio/wav"},
    )
    assert response.status_code == 422
    speech_service.transcribe.assert_called_once()


# failed inference releases capacity so the next request can succeed.
def test_service_failure_returns_503_and_allows_retry(signed_in_client, speech_service, wav_audio):
    speech_service.transcribe.side_effect = [
        SpeechServiceError("private model failure details"),
        speech_service.transcribe.return_value,
    ]
    response = signed_in_client.post(
        "/speech/transcribe", content=wav_audio, headers={"Content-Type": "audio/wav"},
    )
    assert response.status_code == 503
    assert "private model" not in response.text
    assert signed_in_client.app.state.speech_limiter.borrowed_tokens == 0
    retry = signed_in_client.post(
        "/speech/transcribe", content=wav_audio, headers={"Content-Type": "audio/wav"},
    )
    assert retry.status_code == 200


# a missing startup resource must produce a clear service-unavailable response.
def test_missing_service_returns_503(signed_in_client, speech_service, wav_audio):
    del signed_in_client.app.state.speech_service
    try:
        response = signed_in_client.post(
            "/speech/transcribe", content=wav_audio, headers={"Content-Type": "audio/wav"},
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "Speech service is unavailable."
        speech_service.transcribe.assert_not_called()
    finally:
        signed_in_client.app.state.speech_service = speech_service


# blocking inference must not block the server or admit a second transcription.
def test_concurrent_request_returns_429(signed_in_client, speech_service, wav_audio):
    started = Event()
    release = Event()
    expected = speech_service.transcribe.return_value

    def slow_transcription(audio):
        started.set()
        if not release.wait(timeout=10):
            raise SpeechServiceError("test worker timed out")
        return expected

    def submit():
        return signed_in_client.post(
            "/speech/transcribe", content=wav_audio, headers={"Content-Type": "audio/wav"},
        )

    speech_service.transcribe.side_effect = slow_transcription
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(submit)
        try:
            assert started.wait(timeout=5)
            second = pool.submit(submit).result(timeout=5)
            assert second.status_code == 429
            assert second.headers["retry-after"] == "2"
            speech_service.transcribe.assert_called_once()
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 200
    assert signed_in_client.app.state.speech_limiter.borrowed_tokens == 0
