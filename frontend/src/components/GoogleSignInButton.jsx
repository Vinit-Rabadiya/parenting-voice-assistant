// this component displays the google sign-in button and handles the popup login.
// it is imported in pages/AuthPage.jsx so users can log in with their google account.
import { useState } from "react";
import { signInWithGoogle } from "../services/auth";

export default function GoogleSignInButton({ onMfaRequired }) {
  // remember whether this button is waiting and which message to show.
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function handleSignIn() {
    if (busy) return;
    setBusy(true);
    setMessage("Signing in with Google...");
    try {
      const result = await signInWithGoogle();
      // google login may still need an authenticator code before it is complete.
      if (result.next === "mfa-required") {
        setMessage("Enter your authenticator code to finish logging in.");
        onMfaRequired(result.resolver);
      } else if (result.next === "signed-in") {
        setMessage("Signed in successfully!");
      }
    } catch (error) {
      // explain errors in words the user can understand.
      if (error.code === "auth/popup-closed-by-user") {
        setMessage("Sign-in was cancelled. Please try again.");
      } else if (error.code === "auth/popup-blocked") {
        setMessage("Allow popups for this site, then try again");
      } else {
        setMessage("Could not sign in. Please try again.");
      }
    } finally {
      // make the button usable again when the attempt finishes.
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
