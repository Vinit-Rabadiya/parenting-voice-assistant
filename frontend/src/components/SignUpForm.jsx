import { useState } from "react";
import { signUpWithEmail } from "../services/auth";

function SignUpForm({ onAccountCreated }) {
  // this form collects details; the parent decides which screen appears next.
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function handleSubmit(e) {
    // keep the page open and stop repeated submissions while waiting.
    e.preventDefault();
    if (busy) return;

    setBusy(true);
    setMessage("");

    try {
      const result = await signUpWithEmail(email, password);
      // the account can exist even if sending its verification email fails.
      if (result.verificationEmailRequested) {
        setMessage(
          "Account created. Check your inbox and spam folder for the verification link.",
        );
      } else {
        setMessage(
          "Account created, but we couldn’t send the verification email.",
        );
      }
      // tell the parent the account exists so it can show verification instructions.
      onAccountCreated(result);
    } catch (error) {
      // explain which password requirements the user needs to meet.
      if (
        error.code === "auth/weak-password" ||
        error.code === "auth/password-does-not-meet-requirements"
      ) {
        setMessage(
          "Use at least 8 characters, including an uppercase letter, a lowercase letter, a number, and a special character.",
        );
      } else {
        setMessage(
          "Could not complete signup. Please try again or sign in if you already have an account.",
        );
      }
    } finally {
      // let the user correct the form and try again after an error.
      setBusy(false);
    }
  }
  return (
    <form onSubmit={handleSubmit}>
      {/* show the remembered text and update it whenever the user types. */}
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
      <p>
        Use at least 8 characters, including an uppercase letter, a lowercase
        letter, a number, and a special character.
      </p>
      <button type="submit" disabled={busy}>
        Create Account
      </button>
      <p role="status">{message} </p>
    </form>
  );
}

export default SignUpForm;
