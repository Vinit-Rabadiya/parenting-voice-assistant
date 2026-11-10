// receives wav bytes from the transcription hook and returns the speech endpoint's json result.
import { auth } from "./firebase";

export async function transcribeAudio(wavBlob, signal) {
  signal?.throwIfAborted();
  const user = auth.currentUser;
  if (!user) {
    throw new Error("Log in to transcribe audio.");
  }
  const token = await user.getIdToken();
  // do not upload audio if login changed or the request was cancelled while waiting.
  signal?.throwIfAborted();
  if (auth.currentUser !== user) {
    throw new Error("Account changed. Please try again.");
  }

  let response;
  try {
    // send the blob directly because the endpoint expects wav bytes, not a multipart form.
    response = await fetch("/api/speech/transcribe?language=en", {
      method: "POST",
      body: wavBlob,
      headers: {
        "Content-Type": "audio/wav",
        Authorization: `Bearer ${token}`,
      },
      signal,
      credentials: "omit",
      cache: "no-store",
    });
  } catch (cause) {
    if (signal?.aborted) throw cause;
    throw new Error("Could not reach the speech server. Check your connection and try again.", {
      cause,
    });
  }

  signal?.throwIfAborted();
  if (auth.currentUser !== user) {
    throw new Error("Account changed. Please try again.");
  }

  // show a useful message if a proxy or server returns a non-json response.
  let body;
  try {
    body = await response.json();
  } catch (cause) {
    // keep cancellation distinct from a failed server response.
    if (signal?.aborted) throw cause;
    throw new Error("The speech server returned an unreadable response. Please try again.", {
      cause,
    });
  }

  // reading the response may take time, so recheck the account afterward.
  signal?.throwIfAborted();
  if (auth.currentUser !== user) {
    throw new Error("Account changed. Please try again.");
  }
  if (!response.ok) {
    if (typeof body?.detail === "string") {
      throw new Error(body.detail);
    } else {
      throw new Error("Speech transcription failed.");
    }
  }
  // reject malformed successful responses before the interface tries to use them.
  if (
    typeof body?.text !== "string" ||
    !Number.isFinite(body.audio_seconds) || body.audio_seconds <= 0 || body.audio_seconds > 30 ||
    !Number.isFinite(body.processing_seconds) || body.processing_seconds < 0
  ) {
    throw new Error("The speech server returned an unexpected result. Please try again.");
  }
  // the hook uses text and processing_seconds to update the transcript and timing display.
  return body;
}
