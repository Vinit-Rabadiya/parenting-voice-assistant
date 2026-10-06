import pytest
from backend.services.audio_validation import validate_audio
from backend.services.speech_errors import InvalidAudioError

def test_empty_audio_raises_invalid_audio_error():
    with pytest.raises(expected_exception=InvalidAudioError):
        validate_audio(b"")
