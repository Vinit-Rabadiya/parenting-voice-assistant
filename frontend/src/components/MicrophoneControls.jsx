import useMicrophone from "../hooks/useMicrophone";

export default function MicrophoneControls() {
  const { status, error, start, stop } = useMicrophone();
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
    </section>
  );
}
