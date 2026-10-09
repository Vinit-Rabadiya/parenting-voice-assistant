// choose the landing, authentication, or account screen.
// it is imported in main.jsx and rendered into the root element of index.html.
import "./App.css";
import { useState } from "react";
import { AuthProvider } from "./context/AuthProvider";
import { useAuth } from "./hooks/useAuth";
import AccountPage from "./pages/AccountPage";
import AuthPage from "./pages/AuthPage";
import LandingPage from "./pages/LandingPage";
import { Navbar } from "./components/Navbar";
import useAccountAccess from "./hooks/useAccountAccess";

function MainContent() {
  const { user, checkingAuth, signupResult, setSignupResult } = useAuth();
  const [screen, setScreen] = useState("home");
  const [previousUserId, setPreviousUserId] = useState(user?.uid ?? null);
  const accountAccess = useAccountAccess(user);

  // wait for firebase to finish checking who is signed in.
  if (checkingAuth) {
    return <p>Checking sign-in...</p>;
  }

  // logout from any screen returns to the public landing page.
  const userId = user?.uid ?? null;
  if (previousUserId !== userId) {
    setPreviousUserId(userId);
    if (previousUserId !== null && userId === null) {
      setScreen("home");
      return null;
    }
  }

  // account management is not a destination for a signed-out visitor.
  if (screen === "account" && !user) {
    setScreen("home");
    return null;
  }

  // finish authentication at the microphone instead of showing an extra account step.
  // unverified accounts still see onboarding; backend mfa checks remain authoritative.
  if ((screen === "login" || screen === "signup") && user?.emailVerified) {
    setScreen("home");
    return null;
  }

  return (
    <>
      <Navbar
        isAuthenticated={Boolean(user)}
        displayName={user?.displayName || user?.email}
        accountAccess={accountAccess}
        onHome={() => setScreen("home")}
        onLogin={() => setScreen("login")}
        onSignup={() => setScreen("signup")}
        onAccount={() => setScreen("account")}
      />
      {screen === "home" ? (
      <main className="landing-shell">
        <LandingPage
          isAuthenticated={Boolean(user)}
          userId={user?.uid}
          accountAccess={accountAccess}
          onLogin={() => setScreen("login")}
        />
      </main>
      ) : (
    <main>
      <button type="button" onClick={() => setScreen("home")}>
        Back to home
      </button>
      {/* show account page if signed in, otherwise show auth page. */}
      {user ? (
        <AccountPage
          // start with fresh page state when the user changes.
          key={`account-${user.uid}`}
          email={user.email}
          accountAccess={accountAccess}
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
      )}
    </>
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
