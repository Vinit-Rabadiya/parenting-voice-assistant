import { useState } from "react";
import { signUpWithEmail } from "../services/auth";

function SignUpForm() {
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
      const result = await signUpWithEmail(email, password);
      if (result.verificationEmailRequested) {
        setMessage(
          "Account created. Check your inbox and spam folder for the verification link.",
        );
      } else {
        setMessage(
          "Account created, but we couldn’t send the verification email.",
        );
      }
    } catch {
      setMessage(
        "Could not complete signup. Please try again or sign in if you already have an account.",
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
        Create Account
      </button>
      <p role="status">{message} </p>
    </form>
  );
}

export default SignUpForm;
