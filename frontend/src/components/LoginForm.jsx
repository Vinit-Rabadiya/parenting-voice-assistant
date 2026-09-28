// this component handles the email and password inputs, form submission, and password reset trigger.
// it is imported in pages/AuthPage.jsx when the user selects the login view.
import { useState } from "react";
import { signInWithEmail } from "../services/auth";
import { requestPasswordReset } from "../services/auth";

function LoginForm({ onMfaRequired }) {
  // remember what the user types while this form is open.
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function handleSubmit(e) {
    // handle the form here without reloading the page.
    e.preventDefault();
    if (busy) return;

    setBusy(true);
    setMessage("");

    try {
      const result = await signInWithEmail(email, password);
      if (result.next === "mfa-required") {
        // clear the password and ask the parent page to show the code-entry form.
        setPassword("");
        onMfaRequired(result.resolver);
      }
    } catch {
      setMessage(
        "Couldn’t log in. Check your email and password, then try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function handlePasswordReset() {
    // use the entered email to request a reset without needing the old password.
    if (busy) return;

    if (email.trim() === "") {
      setMessage("Enter your email address above first.");
      return;
    }
    setBusy(true);
    setMessage("");

    try {
      await requestPasswordReset(email.trim());
      // show the same response whether or not the email belongs to an account.
      setMessage(
        "If an eligible account exists, you’ll receive a password-reset email. Check your inbox and spam folder.",
      );
    } catch {
      setMessage(
        "Couldn’t request a password reset. Check the email address and try again later.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={handleSubmit}>
      <label>
        Email:
        <input
          value={email}
          type="email"
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      <label>
        Password:
        <input
          value={password}
          type="password"
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <button type="submit" disabled={busy}>
        Log in
      </button>
      {/* this button requests a reset instead of trying to log in. */}
      <button type="button" disabled={busy} onClick={handlePasswordReset}>
        Forgot Password?
      </button>
      <p role="status">{message} </p>
    </form>
  );
}

export default LoginForm;
