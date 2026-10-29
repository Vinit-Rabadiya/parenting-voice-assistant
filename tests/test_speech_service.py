import io
import wave
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.schemas.speech import TranscriptionResponse
from backend.services.speech import SpeechService
from backend.services.speech_errors import SpeechServiceError, InvalidAudioError


# provide a valid recording for the tests to reuse.
@pytest.fixture
def valid_audio():
    # share a one-second wav across service tests without saving a file.
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(bytes(16000 * 2))
    return buffer.getvalue()

# check that a model loading failure becomes a speech service error.
def test_model_loading_failure_raises_service_error():
    with patch(
        "backend.services.speech.WhisperModel",
        side_effect=RuntimeError("model loading failed"),
    ):
        with pytest.raises(SpeechServiceError):
            SpeechService("tiny.en")

# check that empty audio is rejected before transcription starts.
def test_invalid_audio_is_rejected_before_inference():
    with patch("backend.services.speech.WhisperModel") as model_class:
        service = SpeechService("tiny.en")

        with pytest.raises(InvalidAudioError):
            service.transcribe(b"")

        # invalid audio must be rejected before the model receives it.
        model_class.return_value.transcribe.assert_not_called()

# check that successful transcription returns the correct text and timing.
@pytest.mark.parametrize("model_name,fragments,expected", [
    ("tiny.en", [" My baby is ", " six months old. "], "My baby is six months old."),
    ("small", [" Mtoto wangu ", " analia. "], "Mtoto wangu analia."),
    ("small", [" Mtoto wangu analia, ", " what can I do? "], "Mtoto wangu analia, what can I do?"),
])
def test_successful_transcription_returns_text_and_timing(valid_audio, model_name, fragments, expected):
    with patch("backend.services.speech.WhisperModel") as model_class:
        # fake segments let us check text assembly without running inference.
        model = model_class.return_value
        model.transcribe.return_value = (
            iter(SimpleNamespace(text=fragment) for fragment in fragments),
            None,
        )
        service = SpeechService(model_name)

        # fixed clock readings make the elapsed-time check predictable.
        with patch("backend.services.speech.time.perf_counter", side_effect=[100.0, 102.5]):
            result = service.transcribe(valid_audio)

        assert isinstance(result, TranscriptionResponse)
        assert result.text == expected
        assert result.audio_seconds == 1.0
        assert result.processing_seconds == 2.5

        # confirm the original recording reaches the model as a readable buffer.
        model.transcribe.assert_called_once()
        assert model.transcribe.call_args.kwargs == {
            "language": None, "task": "transcribe", "beam_size": 1, "vad_filter": True,
        }
        audio_buffer = model.transcribe.call_args.args[0]
        assert audio_buffer.read() == valid_audio

# check that no recognized words produces an empty transcript.
def test_no_speech_segments_returns_empty_text(valid_audio):
    with patch("backend.services.speech.WhisperModel") as model_class:
        # an empty model result should not create transcript text.
        model_class.return_value.transcribe.return_value = (iter([]), None)
        service = SpeechService("tiny.en")

        result = service.transcribe(valid_audio)

        assert result.text == ""
        assert result.audio_seconds == 1.0
        assert result.processing_seconds >= 0

# check that a failure while reading results becomes a speech service error.
def test_segment_iteration_failure_raises_service_error(valid_audio):
    failure = RuntimeError("segment generation failed")

    # simulate a model that fails after returning some words.
    def failing_segments():
        # fail after one segment to check errors during generator iteration.
        yield SimpleNamespace(text=" My baby")
        raise failure

    with patch("backend.services.speech.WhisperModel") as model_class:
        model_class.return_value.transcribe.return_value = (failing_segments(), None)
        service = SpeechService("tiny.en")

        with pytest.raises(SpeechServiceError, match="Speech transcription failed") as error:
            service.transcribe(valid_audio)

        # retain the original failure for debugging instead of returning partial text.
        assert error.value.__cause__ is failure

# check that two recordings use the same model without loading it again.
def test_multiple_transcriptions_reuse_loaded_model(valid_audio):
    with patch("backend.services.speech.WhisperModel") as model_class:
        model = model_class.return_value
        # each recording needs a fresh iterator because generators are consumed once.
        model.transcribe.side_effect = [
            (iter([SimpleNamespace(text=" First recording.")]), None),
            (iter([SimpleNamespace(text=" Second recording.")]), None),
        ]
        service = SpeechService("tiny.en")

        first = service.transcribe(valid_audio)
        second = service.transcribe(valid_audio)

        assert first.text == "First recording."
        assert second.text == "Second recording."
        # two recordings should use one model instance rather than loading twice.
        model_class.assert_called_once()
        assert model.transcribe.call_count == 2
