// choose the caregiver, administrator, authentication, or account screen.
// it is imported in main.jsx and rendered into the root element of index.html.
import "./App.css";
import { useState } from "react";
import { AuthProvider } from "./context/AuthProvider";
import { useAuth } from "./hooks/useAuth";
import AccountPage from "./pages/AccountPage";
import AuthPage from "./pages/AuthPage";
import LandingPage from "./pages/LandingPage";
import AdminPage from "./pages/AdminPage";
import { Navbar } from "./components/Navbar";
import useAccountAccess from "./hooks/useAccountAccess";
import { stopGuidanceAudio } from "./hooks/useGuidanceAudio";
import { saveChildSelection } from "./services/childSelection";
import EmergencyContacts from "./components/EmergencyContacts";

function MainContent() {
  const { user, checkingAuth, signupResult, setSignupResult } = useAuth();
  const [screen, setScreen] = useState("home");
  const [previousUserId, setPreviousUserId] = useState(user?.uid ?? null);
  const [dataRevision, setDataRevision] = useState(0);
  const [emergencyOpen, setEmergencyOpen] = useState(false);
  const accountAccess = useAccountAccess(user);
  const administrator = accountAccess.verified && accountAccess.role === "administrator";

  // wait for firebase to finish checking who is signed in.
  if (checkingAuth) {
    return <div className="access-loading-screen"><p>Checking sign-in...</p></div>;
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

  if (user && (accountAccess.checking || accountAccess.status === "unavailable")) {
    return <div className="access-loading-screen">
      {accountAccess.checking ? <div role="status" aria-label="Loading">
        <span className="access-spinner" aria-hidden="true" /><span className="visually-hidden">Loading…</span>
      </div> : <><p role="status">Unable to connect.</p>
        <button type="button" onClick={accountAccess.retry}>Retry connection</button></>}
      {!accountAccess.checking && <EmergencyContacts />}
    </div>;
  }

  return (
    <>
      <Navbar
        isAuthenticated={Boolean(user)}
        displayName={user?.displayName || user?.email}
        accountAccess={accountAccess}
        onEmergencyChange={setEmergencyOpen}
        onHome={() => setScreen("home")}
        onLogin={() => setScreen("login")}
        onSignup={() => setScreen("signup")}
        onAccount={() => { stopGuidanceAudio(); setScreen("account"); }}
      />
      {administrator && screen === "home" && <main className="admin-shell"><AdminPage /></main>}
      {!administrator && (user || screen === "home") && (
      <main className="landing-shell" hidden={screen !== "home"} key={`workspace-${userId}-${dataRevision}`}>
        <LandingPage
          isAuthenticated={Boolean(user)}
          userId={user?.uid}
          accountAccess={accountAccess}
          isActive={screen === "home" && !emergencyOpen}
          onLogin={() => setScreen("login")}
          onSignup={() => setScreen("signup")}
        />
      </main>
      )}
      {screen !== "home" && (
    <main className={user ? "account-shell" : undefined}>
      <button className={user ? "account-back" : undefined} type="button" onClick={() => setScreen("home")}>
        {administrator ? "Back to dashboard" : "Back to home"}
      </button>
      {/* show account page if signed in, otherwise show auth page. */}
      {user ? (
        <AccountPage
          // start with fresh page state when the user changes.
          key={`account-${user.uid}`}
          email={user.email}
          accountAccess={accountAccess}
          onDataDeleted={() => { saveChildSelection(user.uid, null); setDataRevision((value) => value + 1); accountAccess.retry?.(); }}
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
