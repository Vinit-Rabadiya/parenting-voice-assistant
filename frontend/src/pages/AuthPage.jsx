// this page displays the login form, signup form, or totp code challenge when signed out.
// app.jsx opens this page when a signed-out visitor chooses login or signup.
import { useState } from "react";
import LoginForm from "../components/LoginForm";
import SignUpForm from "../components/SignUpForm";
import GoogleSignInButton from "../components/GoogleSignInButton";
import { completeTotpSignIn, totpSignInFactors } from "../services/auth";

function AuthPage({ onAccountCreated, initialMode = "login" }) {
  // choose login or signup here; each form calls the shared firebase functions.
  const [mode, setMode] = useState(initialMode);
  // remember the unfinished login while waiting for an authenticator code.
  const [mfaResolver, setMfaResolver] = useState(null);
  const [code, setCode] = useState("");
  const [factorUid, setFactorUid] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  // send the authenticator code to finish login; the app then changes screens.
  const submitHandler = async (e) => {
    e.preventDefault();
    if (busy) return;

    setBusy(true);
    setMessage("");
    try {
      await completeTotpSignIn(mfaResolver, code, factorUid || null);
    } catch {
      setMessage(
        "Couldn’t complete verification. Try a fresh code or cancel and log in again.",
      );
    } finally {
      // clear the typed code and make the button usable again.
      setCode("");
      setBusy(false);
    }
  };
  // show code entry instead of login choices while firebase waits for the code.
  if (mfaResolver) {
    return (
      <section>
        <h1>Enter your authenticator code</h1>

        <form onSubmit={submitHandler}>
          {totpSignInFactors(mfaResolver).length > 1 && <label>Authenticator
            <select value={factorUid || totpSignInFactors(mfaResolver)[0].uid} disabled={busy}
              onChange={(event) => setFactorUid(event.target.value)}>
              {totpSignInFactors(mfaResolver).map((factor, index) => <option key={factor.uid} value={factor.uid}>
                {factor.displayName || `Authenticator ${index + 1}`}</option>)}
            </select>
          </label>}
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
        <details><summary>Lost access to your authenticator?</summary>
          <p>Select your backup authenticator above if you added one. If neither authenticator is available,
            contact the account administrator for identity verification and MFA recovery.
            A password reset does not remove MFA.</p>
        </details>

        <button
          type="button"
          disabled={busy}
          onClick={() => {
            // cancel this login attempt without removing the user's authenticator.
            setMfaResolver(null);
            setCode("");
            setFactorUid("");
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

      {/* both login methods tell this page when an authenticator code is needed. */}
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
