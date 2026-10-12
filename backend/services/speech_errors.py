# shared failures let the endpoint distinguish invalid audio from unavailable speech processing.
class InvalidAudioError(Exception):
    """
    Audio is empty, malformed, in an unsupported format, or exceeds the duration limit
    """

class SpeechServiceError(Exception):
    """
    The model cannot load or transcription fails
    """
