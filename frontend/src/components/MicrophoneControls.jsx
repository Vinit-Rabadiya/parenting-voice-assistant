import useMicrophone from "../hooks/useMicrophone";
import useTranscription from "../hooks/useTranscription";
import MicrophoneButton from "./MicrophoneButton";
import "./MicrophoneControls.css";

export default function MicrophoneControls() {
  const { status, error, start, stop, recording } = useMicrophone();
  const transcription = useTranscription(recording);
  const capturing = status !== "idle";
  const transcribing = transcription.status === "transcribing";
  const recordingNow = status === "recording";
  const buttonBusy = (capturing && !recordingNow) || transcribing;
  const buttonLabel = status === "requesting" ? "Waiting for microphone…"
    : status === "stopping" ? "Stopping recording…"
      : status === "preparing" ? "Preparing audio…"
        : transcribing ? "Transcribing…"
          : recordingNow ? "Stop and transcribe" : "Start recording";
  const microphoneMessages = {
    idle: "Ready to record.",
    requesting: "Requesting microphone access…",
    recording: "Recording… Speak, then press Stop and transcribe.",
    stopping: "Finishing audio capture…",
    preparing: "Preparing your audio…",
  };
  const transcriptionMessages = {
    transcribing: "Transcribing… Your microphone is off.",
    success: transcription.text.trim()
      ? "Transcription complete. Review and edit your words below."
      : "No words to display. If speech was not recognized, try speaking closer to the microphone.",
    error: "Transcription did not complete.",
    cancelled: "Transcription cancelled. You can retry or start a new recording.",
  };
  let sampleCount = 0;

  if (recording) {
    for (const chunk of recording.chunks) {
      sampleCount += chunk.length;
    }
  }
  const durationSeconds = recording ? sampleCount / recording.sampleRate : 0;
  return (
    <section className="microphone-controls" aria-label="Speech to text">
      <p>Record up to 30 seconds. Your words appear after you stop. Starting again replaces the current transcript.</p>
      <MicrophoneButton
        label={buttonLabel}
        recording={recordingNow}
        busy={buttonBusy}
        describedBy="microphone-status"
        onClick={() => {
          if (recordingNow) stop();
          else {
            transcription.cancel();
            void start();
          }
        }}
      />
      {(status === "requesting" || status === "preparing") && (
        <button type="button" onClick={stop}>Cancel recording</button>
      )}
      {transcribing && <button type="button" onClick={transcription.cancel}>Cancel transcription</button>}
      {!capturing && ["error", "cancelled"].includes(transcription.status) && recording?.wavBlob && (
        <button type="button" onClick={transcription.retry}>Retry transcription</button>
      )}
      <p id="microphone-status" role="status">
        {capturing ? microphoneMessages[status] : transcriptionMessages[transcription.status] || microphoneMessages.idle}
      </p>
      {error && <p role="alert">{error}</p>}
      {transcription.error && <p role="alert">{transcription.error}</p>}
      {recording && (
        <p>Recorded {durationSeconds.toFixed(2)} seconds.
          {transcription.processingSeconds !== null && ` Server processing: ${transcription.processingSeconds.toFixed(2)} seconds.`}
        </p>
      )}
      <label htmlFor="speech-transcript">Your transcript</label>
      <textarea
        id="speech-transcript"
        rows={6}
        value={capturing ? "" : transcription.text}
        onChange={(event) => transcription.setText(event.target.value)}
        readOnly={capturing || transcription.status !== "success"}
        placeholder="Your spoken words will appear here after recording."
      />
      <p>Edits stay on this page. They are not submitted to RAG or used for training.</p>
    </section>
  );
}
