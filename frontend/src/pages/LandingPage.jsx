import { Navbar } from "../components/Navbar";
import MicrophoneControls from "../components/MicrophoneControls";
import MicrophoneButton from "../components/MicrophoneButton";
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
          <h2 id="voice-entry-title">What’s on your mind?</h2>
          <p id="voice-entry-help">Log in to record up to 30 seconds of English speech and review the transcript.</p>
          <MicrophoneButton label="Log in to use microphone" onClick={onLogin} describedBy="voice-entry-help" />
        </section>
      )}
    </div>
  );
}
