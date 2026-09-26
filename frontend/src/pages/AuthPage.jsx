import { useState } from "react";
import LoginForm from "../components/LoginForm";
import SignUpForm from "../components/SignUpForm";
import GoogleSignInButton from "../components/GoogleSignInButton";

function AuthPage({ onAccountCreated }) {
  const [mode, setMode] = useState("login");
  return (
    <section>
      {mode === "login" ? <h1>Log In</h1> : <h1>Create Account</h1>}

      <GoogleSignInButton />

      {mode === "login" ? (
        <LoginForm />
      ) : (
        <SignUpForm onAccountCreated={onAccountCreated} />
      )}
      <button
        type="button"
        onClick={() => setMode(mode === "login" ? "signup" : "login")}
      >
        {mode === "login"
          ? "New here? Create an account"
          : "Already registered? Log in"}
      </button>
    </section>
  );
}

export default AuthPage;
