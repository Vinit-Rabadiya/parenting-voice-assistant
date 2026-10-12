# reads a local wav and calls the same speech service as the api, printing the result.
import argparse
from pathlib import Path

from backend.services.speech import SpeechService
from backend.services.speech_errors import InvalidAudioError, SpeechServiceError


def main() -> None:
    parser = argparse.ArgumentParser(description="check speech transcription using a wav recording")
    parser.add_argument("audio_path", type=Path, help="path to the wav recording")

    args = parser.parse_args()

    try:
        audio_bytes = args.audio_path.read_bytes()
    except OSError as exc:
        parser.error(f"could not read audio file: {exc}")

    try:
        service = SpeechService("tiny.en")
        result = service.transcribe(audio_bytes)
    except (InvalidAudioError, SpeechServiceError) as exc:
        parser.exit(status=1, message=f"speech check failed: {exc}\n")

    print("Transcript:", result.text)
    print("Audio duration:", result.audio_seconds, "seconds")
    print("Processing time:", result.processing_seconds, "seconds")


if __name__ == "__main__":
    main()
