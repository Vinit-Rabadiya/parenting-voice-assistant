// receives login state from app.jsx and shows either recording controls or a login button.
import MicrophoneButton from "../components/MicrophoneButton";
import GuidanceWorkspace from "../components/GuidanceWorkspace";
import "./LandingPage.css";

// arrange the landing screen while hooks own recording and network behavior.
export default function LandingPage({ isAuthenticated, userId, accountAccess, onLogin }) {
  return (
    <div className={`landing-page${isAuthenticated ? " landing-page--chat" : ""}`}>
      <section className="landing-intro" aria-labelledby="landing-title">
        <p className="landing-eyebrow">YOUR BABY’S FIRST TWO YEARS</p>
        <h1 id="landing-title">Start with your voice.</h1>
        <p>Speak a question about feeding, sleep, play, or development. Stop recording to see and edit your words.</p>
      </section>
      {isAuthenticated ? (
        <div className="landing-voice">
          {!accountAccess?.verified && (
            <p className="landing-account-note" role="status">
              {accountAccess?.checking ? "Checking your account…" : `${accountAccess?.error || "Complete account verification."} Open My Account for setup.`}
            </p>
          )}
          {/* a changed user key clears private child and question state from the prior account. */}
          <GuidanceWorkspace key={`guidance-${userId}`} />
        </div>
      ) : (
        <section className="landing-voice landing-sign-in" aria-labelledby="voice-entry-title">
          <h2 id="voice-entry-title">What’s on your mind?</h2>
          <p id="voice-entry-help">Log in to record up to 30 seconds of English speech and review the transcript.</p>
          <MicrophoneButton label="Log in to use microphone" onClick={onLogin} describedBy="voice-entry-help" />
        </section>
      )}
    </div>
  );
}
