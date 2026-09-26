import { useState, useEffect } from "react";
import { resendVerificationEmail } from "../services/auth";
import {
  logOut,
  beginTotpEnrollment,
  confirmTotpEnrollment,
  getAccountSecurityStatus,
} from "../services/auth";
function AccountPage({ verificationEmailRequested, email }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [resendSecondsLeft, setResendSecondsLeft] = useState(0);
  const [emailVerified, setEmailVerified] = useState(null);
  const [checkingStatus, setCheckingStatus] = useState(true);
  const [pendingEnrollment, setPendingEnrollment] = useState(null);
  const [enrollmentCode, setEnrollmentCode] = useState("");
  const [enrollmentComplete, setEnrollmentComplete] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function loadVerificationStatus() {
      try {
        const status = await getAccountSecurityStatus();

        if (!cancelled) {
          setEmailVerified(status.emailVerified);
          setEnrollmentComplete(status.totpEnrolled);
        }
      } catch {
        if (!cancelled) {
          setMessage(
            "Couldn’t check your email status. Please try the check button.",
          );
        }
      } finally {
        if (!cancelled) {
          setCheckingStatus(false);
        }
      }
    }
    loadVerificationStatus();

    return () => {
      cancelled = true;
    };
  }, []);

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
      const status = await getAccountSecurityStatus();
      const isVerified = status.emailVerified;

      setEmailVerified(isVerified);
      setEnrollmentComplete(status.totpEnrolled);
      if (isVerified === true) {
        setMessage(
          status.totpEnrolled
            ? "Email verified. Authenticator is enrolled."
            : "Email verified. Set up your authenticator next.",
        );
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

  async function handleBeginEnrollment() {
    if (busy) return;
    setBusy(true);
    setMessage("");
    setEnrollmentCode("");

    try {
      const pending = await beginTotpEnrollment();
      setPendingEnrollment(pending);
    } catch (error) {
      setMessage(
        error.code === "auth/requires-recent-login"
          ? "Log out and log in again before setting up your authenticator."
          : "Couldn’t start authenticator setup. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirmEnrollment(event) {
    event.preventDefault();
    if (busy || !pendingEnrollment) return;

    setBusy(true);
    setMessage("");

    try {
      await confirmTotpEnrollment(pendingEnrollment, enrollmentCode);
      setPendingEnrollment(null);
      setEnrollmentComplete(true);
      setMessage(
        "Authenticator added. Log out, then log in to test your code.",
      );
    } catch {
      setMessage(
        "Couldn’t confirm setup. Try a fresh code, or cancel and start setup again.",
      );
    } finally {
      setEnrollmentCode("");
      setBusy(false);
    }
  }

  if (checkingStatus) {
    return <p role="status">Checking email verification…</p>;
  }

  return (
    <section>
      <h1>Verify your email.</h1>
      <p>Account Email: {email}</p>
      {emailVerified ? (
        <div>
          <p>Email verified.</p>

          {enrollmentComplete ? (
            <p>
              Authenticator enrollment completed. Log out and test MFA login.
            </p>
          ) : pendingEnrollment ? (
            <form onSubmit={handleConfirmEnrollment}>
              <p>
                In your authenticator app, add an account using a setup key.
                Choose a time-based code and use your account email as its
                label.
              </p>

              <p>Setup key:</p>
              <code>{pendingEnrollment.secret.secretKey}</code>

              <p>
                Keep access to your authenticator. A password-reset email will
                not recover a lost authenticator.
              </p>

              <label>
                Authenticator code
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={enrollmentCode}
                  onChange={(event) => setEnrollmentCode(event.target.value)}
                  pattern="[0-9]{6}"
                  maxLength={6}
                  required
                  disabled={busy}
                />
              </label>

              <button type="submit" disabled={busy}>
                Confirm authenticator
              </button>

              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  setPendingEnrollment(null);
                  setEnrollmentCode("");
                  setMessage("");
                }}
              >
                Cancel setup
              </button>
            </form>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={handleBeginEnrollment}
            >
              Set up authenticator
            </button>
          )}
        </div>
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
