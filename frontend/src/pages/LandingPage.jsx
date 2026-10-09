import { Navbar } from "../components/Navbar";
import MicrophoneControls from "../components/MicrophoneControls";
import "./LandingPage.css";

// arrange the landing screen while hooks own recording and network behavior.
export default function LandingPage({ isAuthenticated, userId, onAccount, onLogin, onSignup }) {
  return (
    <div className="landing-page">
      <Navbar
        onLogin={onLogin}
        onSignup={onSignup}
        isAuthenticated={isAuthenticated}
        onAccount={onAccount}
      />
      <section className="landing-intro" aria-labelledby="landing-title">
        <p className="landing-eyebrow">YOUR BABY’S FIRST TWO YEARS</p>
        <h1 id="landing-title">Start with your voice.</h1>
        <p>Speak a question about feeding, sleep, play, or development. Stop recording to see and edit your words.</p>
      </section>
      {isAuthenticated ? (
        <div className="landing-voice">
          <p className="landing-account-note">Voice transcription requires a verified email and authenticator login. Use My Account to finish setup.</p>
          <MicrophoneControls key={`microphone-${userId}`} />
        </div>
      ) : (
        <section className="landing-voice landing-sign-in" aria-labelledby="voice-entry-title">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
            <rect x="9" y="2" width="6" height="12" rx="3" />
            <path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8" />
          </svg>
          <h2 id="voice-entry-title">What’s on your mind?</h2>
          <p id="voice-entry-help">Log in to record up to 30 seconds of English speech and review the transcript.</p>
          <button type="button" onClick={onLogin} aria-describedby="voice-entry-help">Log in to use microphone</button>
        </section>
      )}
    </div>
  );
}
