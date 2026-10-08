import { auth } from "./firebase";

export async function transcribeAudio(wavBlob, signal) {
  const user = auth.currentUser;
  if (!user) {
    throw new Error("Log in to transcribe audio.");
  }
  const token = await user.getIdToken();
  const response = await fetch("/api/speech/transcribe", {
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
  return body;
}
