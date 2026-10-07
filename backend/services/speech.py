import io
import time

from faster_whisper import WhisperModel

from backend.services.speech_errors import SpeechServiceError
from backend.services.audio_validation import validate_audio
from backend.schemas.speech import TranscriptionResponse


class SpeechService:
    def __init__(self, model_name: str) -> None:
        try:
            self._model = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                cpu_threads=2,
                num_workers=1,
            )
        except Exception as exc:
            raise SpeechServiceError("Could not load the speech recognition model.") from exc

    def transcribe(self, audio_bytes: bytes) -> TranscriptionResponse:
        audio_seconds = validate_audio(audio_bytes)
        audio_buffer = io.BytesIO(audio_bytes)
        started_at = time.perf_counter()
        try:
            # transcribe using the model already loaded by the constructor.
            segments, _ = self._model.transcribe(
                audio_buffer,
                language="en",
                beam_size=1,
                vad_filter=True,
            )

            # reading the segments runs inference and collects the words.
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

        except Exception as exc:
            raise SpeechServiceError("Speech transcription failed.") from exc

        return TranscriptionResponse(
            text=" ".join(text_parts),
            audio_seconds=audio_seconds,
            processing_seconds=time.perf_counter() - started_at,
        )
