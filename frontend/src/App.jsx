import "./App.css";
import GoogleSignInButton from "./components/GoogleSignInButton";
import { useState } from "react";
import SignUpForm from "./components/SignUpForm";
import VerifyEmailPage from "./pages/VerifyEmailPage";

function App() {
  const [signupResult, setSignupResult] = useState(null);
  return (
    <main>
      <h1>Parenting Voice Assistant</h1>
      <GoogleSignInButton />

      {signupResult ? (
        <VerifyEmailPage
          verificationEmailRequested={signupResult.verificationEmailRequested}
        />
      ) : (
        <SignUpForm onAccountCreated={setSignupResult} />
      )}
    </main>
  );
}
export default App;
