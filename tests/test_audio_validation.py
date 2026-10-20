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
    # build test audio in memory without creating a file.
    buffer = io.BytesIO()
    # convert seconds into the number of audio frames.
    frame_count = int(duration_seconds * sample_rate)

    # write a wav header using the requested audio properties.
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)

        # generate sample bytes; speech is not needed to test the file format.
        audio_data = bytes(frame_count * channels * sample_width)
        wav_file.writeframes(audio_data)

    # return the bytes after the writer finishes the wav header.
    return buffer.getvalue()


def test_empty_audio_raises_invalid_audio_error():
    # Missing audio must raise the shared validation error.
    with pytest.raises(expected_exception=InvalidAudioError):
        validate_audio(b"")


def test_valid_audio_returns_duration():
    # a valid one-second recording should return its duration.
    audio_bytes = make_wav()
    duration = validate_audio(audio_bytes)
    assert duration == 1.0


def test_audio_at_duration_limit_is_accepted():
    # exactly 30 seconds is still allowed.
    audio_bytes = make_wav(duration_seconds=30)
    duration = validate_audio(audio_bytes)
    assert duration == 30.0


def test_audio_over_duration_limit_is_rejected():
    # recordings longer than 30 seconds must be rejected.
    audio_bytes = make_wav(duration_seconds=31)
    with pytest.raises(InvalidAudioError):
        validate_audio(audio_bytes)


def test_stereo_audio_is_rejected():
    # Two channels do not meet the mono audio requirement.
    audio_bytes = make_wav(channels=2)
    with pytest.raises(InvalidAudioError):
        validate_audio(audio_bytes)


def test_wrong_sample_width_is_rejected():
    # one-byte samples are 8-bit rather than the required 16-bit.
    audio_bytes = make_wav(sample_width=1)
    with pytest.raises(InvalidAudioError):
        validate_audio(audio_bytes)


def test_wrong_sample_rate_is_rejected():
    # 8000 Hz does not meet the 16000 Hz requirement.
    audio_bytes = make_wav(sample_rate=8000)
    with pytest.raises(InvalidAudioError):
        validate_audio(audio_bytes)


def test_zero_duration_is_rejected():
    # a wav header without any audio frames is not a valid recording.
    audio_bytes = make_wav(duration_seconds=0)
    with pytest.raises(InvalidAudioError):
        validate_audio(audio_bytes)


def test_malformed_audio_is_rejected():
    # ordinary text bytes cannot be read as a wav recording.
    with pytest.raises(InvalidAudioError):
        validate_audio(b"not a wav recording")


def test_truncated_audio_is_rejected():
    # remove audio bytes without updating the header to simulate a cut-off file.
    audio_bytes = make_wav()[:-10]
    with pytest.raises(InvalidAudioError):
        validate_audio(audio_bytes)
