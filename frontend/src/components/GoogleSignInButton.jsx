import { useState } from "react";
import { signInWithGoogle } from "../services/auth";

export default function GoogleSignInButton() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function handleSignIn() {
    setBusy(true);
    setMessage("Signing in with Google...");
    try {
      await signInWithGoogle();
      setMessage("Signed in successfully!");
    } catch (error) {
      if (error.code === "auth/popup-closed-by-user") {
        setMessage("Sign-in was cancelled. Please try again.");
      } else if (error.code === "auth/popup-blocked") {
        setMessage("Allow popups for this site, then try again");
      } else {
        setMessage("Could not sign in. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <section>
      <button onClick={handleSignIn} disabled={busy}>
        {busy ? "Signing in..." : "Sign in with Google"}
      </button>
      <p role="status">{message}</p>
    </section>
  );
}
