// sends the recording through services/transcription.js and returns editable text and request state.
import { useCallback, useEffect, useRef, useState } from "react";
import { transcribeAudio } from "../services/transcription";

const REQUEST_TIMEOUT_MS = 60000;
const EMPTY_RESULT = { source: null, status: "idle", text: "", error: "", processingSeconds: null };

// submit each completed recording and keep request state out of microphone capture.
export default function useTranscription(recording) {
  const [result, setResult] = useState(EMPTY_RESULT);
  const [attempt, setAttempt] = useState(0);
  const requestRef = useRef(null);

  // rerun when a completed recording arrives or the user requests another attempt.
  useEffect(() => {
    if (!recording?.wavBlob) return;
    const controller = new AbortController();
    requestRef.current = controller;
    const current = () => requestRef.current === controller && !controller.signal.aborted;

    // bound the whole wait, including token retrieval and reading the response body.
    const timer = setTimeout(() => {
      if (!current()) return;
      controller.abort();
      requestRef.current = null;
      setResult({
        ...EMPTY_RESULT, source: recording, status: "error",
        error: "Transcription timed out. Please retry or record a shorter sentence.",
      });
    }, REQUEST_TIMEOUT_MS);
    controller.signal.addEventListener("abort", () => clearTimeout(timer), { once: true });

    // defer submission so react's development cleanup can cancel its first setup.
    async function submit() {
      await Promise.resolve();
      if (!current()) return;
      setResult({ ...EMPTY_RESULT, source: recording, status: "transcribing" });
      try {
        const response = await transcribeAudio(recording.wavBlob, controller.signal);
        if (!current()) return;
        setResult({
          source: recording, status: "success", text: response.text,
          error: "", processingSeconds: response.processing_seconds,
        });
      } catch (cause) {
        if (!current()) return;
        setResult({
          ...EMPTY_RESULT, source: recording, status: "error",
          error: cause.message || "Speech transcription failed. Please try again.",
        });
      } finally {
        clearTimeout(timer);
        if (requestRef.current === controller) requestRef.current = null;
      }
    }
    void submit();

    // discard obsolete results on a new recording, logout, or leaving the page.
    return () => {
      clearTimeout(timer);
      controller.abort();
      if (requestRef.current === controller) requestRef.current = null;
    };
  }, [recording, attempt]);

  const cancel = useCallback(() => {
    requestRef.current?.abort();
    requestRef.current = null;
    setResult({ ...EMPTY_RESULT, source: recording, status: "cancelled" });
  }, [recording]);

  const retry = useCallback(() => {
    if (requestRef.current || !recording?.wavBlob) return;
    setResult({ ...EMPTY_RESULT, source: recording, status: "transcribing" });
    setAttempt((value) => value + 1);
  }, [recording]);

  // editing changes local display state; it does not send another request or train the model.
  const setText = useCallback((text) => {
    setResult((previous) => previous.source === recording && previous.status === "success"
      ? { ...previous, text } : previous);
  }, [recording]);

  // do not display the previous recording's transcript while the new effect starts.
  const visible = !recording?.wavBlob ? EMPTY_RESULT : result.source === recording
    ? result : { ...EMPTY_RESULT, status: "transcribing" };

  return { ...visible, cancel, retry, setText };
}
