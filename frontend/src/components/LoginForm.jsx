import { useState } from "react";
import { signInWithEmail } from "../services/auth";

function LoginForm() {
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
      await signInWithEmail(email, password);
    } catch {
      setMessage(
        "Couldn’t log in. Check your email and password, then try again.",
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
      <p role="status">{message} </p>
    </form>
  );
}

export default LoginForm;
