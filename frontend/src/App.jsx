import "./App.css";
import { AuthProvider } from "./context/AuthProvider";
import { useAuth } from "./hooks/useAuth";
import AccountPage from "./pages/AccountPage";
import AuthPage from "./pages/AuthPage";

function MainContent() {
  const { user, checkingAuth, signupResult, setSignupResult } = useAuth();

  // wait for firebase to finish checking who is signed in.
  if (checkingAuth) {
    return <p>Checking sign-in...</p>;
  }

  return (
    <main>
      <h1>Parenting Voice Assistant</h1>

      {/* show account page if signed in, otherwise show auth page. */}
      {user ? (
        <AccountPage
          // start with fresh page state when the user changes.
          key={user.uid}
          email={user.email}
          // pass email status only if it belongs to this user.
          verificationEmailRequested={
            signupResult?.user.uid === user.uid
              ? signupResult.verificationEmailRequested
              : undefined
          }
        />
      ) : (
        <AuthPage onAccountCreated={setSignupResult} />
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
