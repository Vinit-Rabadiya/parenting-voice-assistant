import { useState } from "react";
import LoginForm from "../components/LoginForm";
import SignUpForm from "../components/SignUpForm";
import GoogleSignInButton from "../components/GoogleSignInButton";
import { completeTotpSignIn } from "../services/auth";

function AuthPage({ onAccountCreated }) {
  const [mode, setMode] = useState("login");
  const [mfaResolver, setMfaResolver] = useState(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const submitHandler = async (e) => {
    e.preventDefault();
    if (busy) return;

    setBusy(true);
    setMessage("");
    try {
      await completeTotpSignIn(mfaResolver, code);
    } catch {
      setMessage(
        "Couldn’t complete verification. Try a fresh code or cancel and log in again.",
      );
    } finally {
      setCode("");
      setBusy(false);
    }
  };
  if (mfaResolver) {
    return (
      <section>
        <h1>Enter your authenticator code</h1>

        <form onSubmit={submitHandler}>
          <label>
            Six-digit code
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              pattern="[0-9]{6}"
              maxLength={6}
              required
              disabled={busy}
            />
          </label>

          <button type="submit" disabled={busy}>
            {busy ? "Verifying…" : "Verify and log in"}
          </button>
        </form>

        <p role="status">{message}</p>

        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setMfaResolver(null);
            setCode("");
            setMessage("");
          }}
        >
          Cancel
        </button>
      </section>
    );
  }
  return (
    <section>
      {mode === "login" ? <h1>Log In</h1> : <h1>Create Account</h1>}

      <GoogleSignInButton onMfaRequired={setMfaResolver} />

      {mode === "login" ? (
        <LoginForm onMfaRequired={setMfaResolver} />
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
