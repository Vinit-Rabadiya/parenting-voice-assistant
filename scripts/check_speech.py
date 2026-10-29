# reads a local wav and calls the same speech service as the api, printing the result.
import argparse
from pathlib import Path
from backend.core.config import settings

from backend.services.speech import SpeechService
from backend.services.speech_errors import InvalidAudioError, SpeechServiceError


def main() -> None:
    parser = argparse.ArgumentParser(description="check speech transcription using a wav recording")
    parser.add_argument("audio_path", type=Path, help="path to the wav recording")
    parser.add_argument("--model", default=settings.STT_MODEL, help="speech model to load")
    parser.add_argument("--language", choices=("en", "sw", "auto"), default="en")

    args = parser.parse_args()

    try:
        audio_bytes = args.audio_path.read_bytes()
    except OSError as exc:
        parser.error(f"could not read audio file: {exc}")

    try:
        service = SpeechService(args.model)
        result = service.transcribe(audio_bytes, language=args.language)
    except (InvalidAudioError, SpeechServiceError) as exc:
        parser.exit(status=1, message=f"speech check failed: {exc}\n")

    print("Model:", args.model)
    print("Language:", args.language)
    print("Transcript:", result.text)
    print("Audio duration:", result.audio_seconds, "seconds")
    print("Processing time:", result.processing_seconds, "seconds")


if __name__ == "__main__":
    main()
