import "./MicrophoneButton.css";

// share the same voice control for guests and signed-in caregivers.
export default function MicrophoneButton({ label, onClick, recording = false, busy = false, describedBy }) {
  return (
    <button
      type="button"
      className={`microphone-button${recording ? " microphone-button--recording" : ""}`}
      onClick={onClick}
      disabled={busy}
      aria-describedby={describedBy}
    >
      <span className="microphone-button__circle" aria-hidden="true">
        {recording ? (
          <svg width="36" height="36" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="6" width="12" height="12" rx="2" />
          </svg>
        ) : (
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <rect x="9" y="2" width="6" height="12" rx="3" />
            <path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8" />
          </svg>
        )}
      </span>
      <span>{label}</span>
    </button>
  );
}
