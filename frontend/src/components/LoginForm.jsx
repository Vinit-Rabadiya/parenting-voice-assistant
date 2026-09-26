import { useState } from "react";
import { signInWithEmail } from "../services/auth";
import { requestPasswordReset } from "../services/auth";

function LoginForm({ onMfaRequired }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (busy) return;

    setBusy(true);
    setMessage("");

    try {
      const result = await signInWithEmail(email, password);
      if (result.next === "mfa-required") {
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
    if (busy) return;

    if (email.trim() === "") {
      setMessage("Enter your email address above first.");
      return;
    }
    setBusy(true);
    setMessage("");

    try {
      await requestPasswordReset(email.trim());
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
      <button type="button" disabled={busy} onClick={handlePasswordReset}>
        Forgot Password?
      </button>
      <p role="status">{message} </p>
    </form>
  );
}

export default LoginForm;
