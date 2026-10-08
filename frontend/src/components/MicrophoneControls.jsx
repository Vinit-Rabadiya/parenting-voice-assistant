import useMicrophone from "../hooks/useMicrophone";

export default function MicrophoneControls() {
  const { status, error, start, stop, recording } = useMicrophone();
  let sampleCount = 0;

  if (recording) {
    for (const chunk of recording.chunks) {
      sampleCount += chunk.length;
    }
  }
  const durationSeconds = recording ? sampleCount / recording.sampleRate : 0;
  return (
    <section>
      <button type="button" onClick={start} disabled={status !== "idle"}>
        Enable Microphone
      </button>
      <button type="button" onClick={stop} disabled={status === "idle"}>
        Stop Microphone
      </button>
      <p role="status">{status}</p>
      {error && <p role="alert">{error}</p>}
      {recording && (
  <p>Recorded {durationSeconds.toFixed(2)} seconds.</p>
)}
    </section>
  );
}
