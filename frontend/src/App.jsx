import "./App.css";
import { useState, useEffect } from "react";
import AccountPage from "./pages/AccountPage";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "./services/firebase";
import AuthPage from "./pages/AuthPage";

function App() {
  const [signupResult, setSignupResult] = useState(null);
  const [user, setUser] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
      setCheckingAuth(false);
    });
    return unsubscribe;
  }, []);

  if (checkingAuth) {
    return <p>Checking sign-in...</p>;
  }
  return (
    <main>
      <h1>Parenting Voice Assistant</h1>

      {user ? (
        <AccountPage
          key={user.uid}
          email={user.email}
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
