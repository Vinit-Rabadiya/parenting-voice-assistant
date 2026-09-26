import { useState, useEffect } from "react";
import { checkEmailVerification } from "../services/auth";
import { resendVerificationEmail } from "../services/auth";
import { logOut } from "../services/auth";
function AccountPage({ verificationEmailRequested, email }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [resendSecondsLeft, setResendSecondsLeft] = useState(0);
  const [emailVerified, setEmailVerified] = useState(null);

  useEffect(() => {
    if (resendSecondsLeft <= 0) return;
    const timerID = setTimeout(() => {
      setResendSecondsLeft((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    return () => clearTimeout(timerID);
  }, [resendSecondsLeft]);

  async function handleCheckVerification() {
    if (busy) return;
    setBusy(true);
    setMessage("");
    try {
      const isVerified = await checkEmailVerification();
      setEmailVerified(isVerified);
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
    if (busy || resendSecondsLeft > 0) {
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const result = await resendVerificationEmail();
      if (result.status === "already-verified") {
        setEmailVerified(true);
        setMessage("Your email is already verified.");
      } else if (result.status === "email-requested") {
        setMessage(
          "Verification email requested. Check your inbox and spam folder.",
        );

        setResendSecondsLeft(60);
      }
    } catch {
      setMessage(
        "Couldn’t resend the verification email. Please try again later.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleLogOut() {
    if (busy) return;
    setBusy(true);
    setMessage("");

    try {
      await logOut();
    } catch {
      setMessage("Couldn't log out. Please try again");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>Verify your email.</h1>
      <p>Account Email: {email}</p>
      {emailVerified ? (
        <p>Email verified. Authenticator setup is next.</p>
      ) : (
        <div>
          {verificationEmailRequested === true ? (
            <p>Check your inbox and spam folder for the verification link.</p>
          ) : verificationEmailRequested === false ? (
            <p>Account created, but we couldn’t send the verification email.</p>
          ) : (
            <p>
              Verify your email to continue. You can check its status or request
              a verification email below.
            </p>
          )}

          <button
            type="button"
            disabled={busy}
            onClick={handleCheckVerification}
          >
            Check Verification Status
          </button>

          <button
            type="button"
            disabled={busy || resendSecondsLeft > 0}
            onClick={handleResendVerification}
          >
            Resend Verification Email
          </button>
          {resendSecondsLeft > 0 ? (
            <p>Resend in {resendSecondsLeft} seconds</p>
          ) : null}
        </div>
      )}
      <p role="status">{message}</p>
      <button type="button" disabled={busy} onClick={handleLogOut}>
        Log Out
      </button>
    </section>
  );
}

export default AccountPage;
