import { Navbar } from "../components/Navbar";

export default function LandingPage({ isAuthenticated, onAccount, onLogin, onSignup }) {
  return (
    <div>
      <Navbar
        onLogin={onLogin}
        onSignup={onSignup}
        isAuthenticated={isAuthenticated}
        onAccount={onAccount}
      />
      <section>
        <h1>Welcome...</h1>
        <p>Speak a question and review the words captured.</p>
      </section>
    </div>
  );
}
