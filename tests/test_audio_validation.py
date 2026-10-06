import io
import wave

import pytest

from backend.services.audio_validation import validate_audio
from backend.services.speech_errors import InvalidAudioError


def make_wav(
    duration_seconds: float = 1.0,
    channels: int = 1,
    sample_width: int = 2,
    sample_rate: int = 16000,
) -> bytes:
    buffer = io.BytesIO()
    frame_count = int(duration_seconds * sample_rate)

    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)

        audio_data = bytes(frame_count * channels * sample_width)
        wav_file.writeframes(audio_data)

    return buffer.getvalue()


def test_empty_audio_raises_invalid_audio_error():
    with pytest.raises(expected_exception=InvalidAudioError):
        validate_audio(b"")


def test_valid_audio_returns_duration():
    audio_bytes = make_wav()
    duration = validate_audio(audio_bytes)
    assert duration == 1.0
