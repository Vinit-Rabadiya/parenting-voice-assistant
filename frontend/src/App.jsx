import "./App.css";
import { useState, useEffect } from "react";
import AccountPage from "./pages/AccountPage";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "./services/firebase";
import AuthPage from "./pages/AuthPage";

function App() {
  // remember signup feedback separately from the currently signed-in user.
  const [signupResult, setSignupResult] = useState(null);
  const [user, setUser] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);

  // ask firebase to tell us who is signed in, including after a page reload.
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
      setCheckingAuth(false);
    });
    // stop listening when react removes this component.
    return unsubscribe;
  }, []);

  // wait for firebase's first answer before choosing a screen.
  if (checkingAuth) {
    return <p>Checking sign-in...</p>;
  }
  return (
    <main>
      <h1>Parenting Voice Assistant</h1>

      {/* choose the screen; the backend still checks login on private requests. */}
      {user ? (
        <AccountPage
          // reset the page's memory when a different user logs in.
          key={user.uid}
          email={user.email}
          // show signup feedback only if it belongs to this user.
          verificationEmailRequested={
            signupResult?.user.uid === user.uid
              ? signupResult.verificationEmailRequested
              : undefined
          }
        />
      ) : (
        <>
          <AuthPage onAccountCreated={setSignupResult} />
        </>
      )}
    </main>
  );
}
export default App;
