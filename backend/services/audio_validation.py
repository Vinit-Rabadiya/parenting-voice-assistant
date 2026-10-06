import io
import wave

from backend.services.speech_errors import InvalidAudioError


def validate_audio(audio_bytes: bytes) -> float:
    """check wav audio and return its duration, or raise an error if invalid."""
    # reject empty audio.
    if not audio_bytes:
        raise InvalidAudioError("Audio recording is empty.")
    try:
        # read audio in memory without saving a file.
        audio_buffer = io.BytesIO(audio_bytes)
        # close the reader automatically when finished.
        with wave.open(audio_buffer, "rb") as wav_file:
            # read the audio properties from the wav header.
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            compression_type = wav_file.getcomptype()

            # require mono, 16-bit audio at 16000 hz.
            if channels != 1:
                raise InvalidAudioError("Audio must be mono.")
            if sample_width != 2:
                raise InvalidAudioError("Audio must use 16-bit samples.")
            if sample_rate != 16000:
                raise InvalidAudioError("Audio sample rate must be 16000 Hz.")
            # require uncompressed audio.
            if compression_type != "NONE":
                raise InvalidAudioError("Audio must use uncompressed PCM.")

            # divide frames by sample rate to get seconds.
            duration_seconds = frame_count / sample_rate

            # accept recordings longer than zero and up to 30 seconds.
            if duration_seconds <= 0:
                raise InvalidAudioError("Audio recording contains no samples.")
            if duration_seconds > 30:
                raise InvalidAudioError("Audio recording must not exceed 30 seconds.")

            # check that all audio bytes promised by the header are present.
            expected_bytes = frame_count * channels * sample_width
            audio_data = wav_file.readframes(frame_count)

            if len(audio_data) != expected_bytes:
                raise InvalidAudioError("Audio recording is incomplete or truncated.")

            # return the duration for the transcription result.
            return duration_seconds
    except (wave.Error, EOFError) as exc:
        # convert wav reading failures to our shared audio error.
        raise InvalidAudioError("Audio must be a valid PCM WAV recording.") from exc

