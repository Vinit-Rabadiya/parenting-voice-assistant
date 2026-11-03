// Show a public introduction or the authenticated caregiver workspace.
import GuidanceWorkspace from "../components/GuidanceWorkspace";
import "./LandingPage.css";

// arrange the landing screen while hooks own recording and network behavior.
export default function LandingPage({ isAuthenticated, userId, accountAccess, onLogin, onSignup, isActive = true }) {
  if (!isAuthenticated) {
    return <div className="landing-page landing-page--guest">
      <div className="guest-hero">
        <section className="guest-intro" aria-labelledby="guest-title">
          <p className="landing-eyebrow">FOR PARENTS AND CAREGIVERS</p>
          <h1 id="guest-title">Support for your baby’s first two years.</h1>
          <p className="guest-description">Ask about feeding, sleep, play and development. Get guidance that takes your child’s age into account, and keep your conversations in one place.</p>
          <div className="guest-actions">
            <button type="button" className="guest-primary" onClick={onSignup}>Create account</button>
            <button type="button" onClick={onLogin}>Log in to your account</button>
          </div>
          <p className="guest-emergency-note">Emergency contacts are available above, without an account.</p>
        </section>
        <section className="guest-topics" aria-labelledby="guest-topics-title">
          <h2 id="guest-topics-title">Here for the everyday questions.</h2>
          <dl>
            <div><dt>Feeding and nutrition</dt><dd>Breastfeeding, meals and growing appetites.</dd></div>
            <div><dt>Sleep and routines</dt><dd>Daily rhythms, bathing and settling down.</dd></div>
            <div><dt>Play and development</dt><dd>Talking, movement and learning together.</dd></div>
            <div><dt>Health and safety</dt><dd>Common concerns, vaccinations and when to seek care.</dd></div>
          </dl>
        </section>
      </div>
      <section className="guest-steps" aria-labelledby="guest-steps-title">
        <h2 id="guest-steps-title">How it works</h2>
        <ol>
          <li><h3>Create your account</h3><p>Sign up to start your own conversations.</p></li>
          <li><h3>Add your child</h3><p>A child profile helps tailor guidance to their age.</p></li>
          <li><h3>Start a conversation</h3><p>Type or speak, listen to replies and return to saved chats.</p></li>
        </ol>
      </section>
    </div>;
  }
  return (
    <div className="landing-page landing-page--chat">
      <section className="landing-intro" aria-labelledby="landing-title">
        <p className="landing-eyebrow">YOUR BABY’S FIRST TWO YEARS</p>
        <h1 id="landing-title">Start with your voice.</h1>
        <p>Speak a question about feeding, sleep, play, or development. Stop recording to see and edit your words.</p>
      </section>
        <div className="landing-voice">
          {!accountAccess?.verified && (
            <p className="landing-account-note" role="status">
              {accountAccess?.checking ? "Checking your account…" : `${accountAccess?.error || "Complete account verification."} Open My Account for setup.`}
            </p>
          )}
          {/* a changed user key clears private child and question state from the prior account. */}
          {accountAccess?.verified && <GuidanceWorkspace key={`guidance-${userId}`} userId={userId} isActive={isActive} startup={accountAccess.startup} />}
        </div>
    </div>
  );
}
