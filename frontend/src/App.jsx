// this is the root view component that switches between the account page and the auth page.
// it is imported in main.jsx and rendered into the root element of index.html.
import "./App.css";
import { useState } from "react";
import { AuthProvider } from "./context/AuthProvider";
import { useAuth } from "./hooks/useAuth";
import AccountPage from "./pages/AccountPage";
import AuthPage from "./pages/AuthPage";
import MicrophoneControls from "./components/MicrophoneControls";
import LandingPage from "./pages/LandingPage";

function MainContent() {
  const { user, checkingAuth, signupResult, setSignupResult } = useAuth();
  const [screen, setScreen] = useState("home");

  // wait for firebase to finish checking who is signed in.
  if (checkingAuth) {
    return <p>Checking sign-in...</p>;
  }
  if (screen === "home") {
    return (
      <main>
        <LandingPage
          isAuthenticated={Boolean(user)}
          onLogin={() => setScreen("login")}
          onSignup={() => setScreen("signup")}
          onAccount={() => setScreen("account")}
        />
        {user && <MicrophoneControls key={`microphone-${user.uid}`} />}
      </main>
    );
  }
  return (
    <main>
      <button type="button" onClick={() => setScreen("home")}>
        Back to home
      </button>
      <h1>Parenting Voice Assistant</h1>
      {/* show account page if signed in, otherwise show auth page. */}
      {user ? (
        <AccountPage
          // start with fresh page state when the user changes.
          key={`account-${user.uid}`}
          email={user.email}
          // pass email status only if it belongs to this user.
          verificationEmailRequested={
            signupResult?.user.uid === user.uid
              ? signupResult.verificationEmailRequested
              : undefined
          }
        />
      ) : (
        <AuthPage
          onAccountCreated={setSignupResult}
          key={screen}
          initialMode={screen === "signup" ? "signup" : "login"}
        />
      )}
    </main>
  );
}

function App() {
  return (
    <AuthProvider>
      <MainContent />
    </AuthProvider>
  );
}

export default App;
