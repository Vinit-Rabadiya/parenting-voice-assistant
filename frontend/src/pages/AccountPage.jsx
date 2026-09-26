import { useState } from "react";
import { checkEmailVerification } from "../services/auth";
import { resendVerificationEmail } from "../services/auth";
function AccountPage({ verificationEmailRequested }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  

  async function handleCheckVerification() {
    if (busy) return;
    setBusy(true);
    setMessage("");
    try {
      const isVerified = await checkEmailVerification();
      if (isVerified === true) {
        setMessage("Your email is verified. Authenticator setup is next.");
      } else {
        setMessage(
          "Your email isn’t verified yet. Open the email link, then check again.",
        );
      }
    } catch {
      setMessage(
        "We couldn’t check your verification status. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleResendVerification() {
    if (busy) {
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const result = await resendVerificationEmail();
      if (result.status === "already-verified") {
        setMessage("Your email is already verified.");
      } else if (result.status === "email-requested") {
        setMessage(
          "Verification email requested. Check your inbox and spam folder.",
        );
      }
    } catch {
      setMessage(
        "Couldn’t resend the verification email. Please try again later.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>Verify your email.</h1>

      {verificationEmailRequested ? (
        <p>Check your inbox and spam folder for the verification link.</p>
      ) : (
        <p>Account created, but we couldn’t send the verification email.</p>
      )}

      <button type="button" disabled={busy} onClick={handleCheckVerification}>
        Check Verification Status
      </button>
      <p role="status">{message}</p>

      <button type="button" disabled={busy} onClick={handleResendVerification}>
        Resend Verification Email
      </button>
    </section>
  );
}

export default AccountPage;
