# converts validated wav bytes into a transcription response using one reusable whisper model.
# called by the speech endpoint and scripts/check_speech.py.
import io
import logging
import os
import time

from faster_whisper import WhisperModel

from backend.services.speech_errors import SpeechServiceError
from backend.services.audio_validation import validate_audio
from backend.schemas.speech import SpeechLanguage, TranscriptionResponse

logger = logging.getLogger("uvicorn.error")


class SpeechService:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        cpu_threads = min(4, os.cpu_count() or 1)
        # model loading happens when the service is created, before individual transcriptions.
        try:
            self._model = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                cpu_threads=cpu_threads,
                num_workers=1,
            )
        except Exception as exc:
            raise SpeechServiceError("Could not load the speech recognition model.") from exc
        logger.info("speech_model model=%s cpu_threads=%d", model_name, cpu_threads)

    def transcribe(self, audio_bytes: bytes, language: SpeechLanguage = "en") -> TranscriptionResponse:
        # validation returns duration and raises an audio error before inference for invalid wavs.
        audio_seconds = validate_audio(audio_bytes)
        audio_buffer = io.BytesIO(audio_bytes)
        started_at = time.perf_counter()
        try:
            multilingual = self._model.model.is_multilingual
            if language == "sw" and not multilingual:
                raise SpeechServiceError("Kiswahili requires a multilingual speech model.")
            # transcribe using the model already loaded by the constructor.
            segments, info = self._model.transcribe(
                audio_buffer,
                # A selected language avoids guessing; automatic mode permits language changes.
                language=None if language == "auto" else language,
                task="transcribe",
                multilingual=bool(multilingual) and language == "auto",
                beam_size=3,
                # One decoding attempt avoids repeated temperature fallbacks on difficult audio.
                temperature=0.0,
                best_of=1,
                condition_on_previous_text=False,
                vad_filter=True,
            )

            # reading the segments runs inference and collects the words.
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

        except SpeechServiceError:
            raise
        except Exception as exc:
            raise SpeechServiceError("Speech transcription failed.") from exc

        processing_seconds = time.perf_counter() - started_at
        # Diagnostics contain model/language/timing only, never audio or transcript text.
        logger.info(
            "speech_timing model=%s language=%s detected_language=%s audio_seconds=%.3f seconds=%.3f",
            self._model_name, language, getattr(info, "language", "unknown"),
            audio_seconds, processing_seconds,
        )
        # the schema checks the result fields before the endpoint sends them as json.
        return TranscriptionResponse(
            text=" ".join(text_parts),
            audio_seconds=audio_seconds,
            processing_seconds=processing_seconds,
        )
