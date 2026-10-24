// this page manages email verification, qr authenticator setup, backend checks, and logout.
// app.jsx opens this page for account management or signed-in onboarding.
import { useState, useEffect } from "react";
import { resendVerificationEmail } from "../services/auth";
import { useAuth } from "../hooks/useAuth";
import {
  beginTotpEnrollment,
  confirmTotpEnrollment,
  getAccountSecurityStatus,
} from "../services/auth";
import QRCode from "qrcode";
import AccountUsage from "../components/AccountUsage";
import AccountConsent from "../components/AccountConsent";
import AdminFeedbackSummary from "../components/AdminFeedbackSummary";
import { deleteAccount, deleteMyData } from "../services/caregiving";
function AccountPage({ verificationEmailRequested, email, accountAccess, onDataDeleted }) {
  const { logout } = useAuth();
  // remember this screen's progress, messages, and account setup details.
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [resendSecondsLeft, setResendSecondsLeft] = useState(0);
  const [emailVerified, setEmailVerified] = useState(null);
  const [checkingStatus, setCheckingStatus] = useState(true);
  // keep the setup key and qr only while setup is open.
  const [pendingEnrollment, setPendingEnrollment] = useState(null);
  const [enrollmentCode, setEnrollmentCode] = useState("");
  // null means authenticator enrollment has not been checked yet.
  const [enrollmentComplete, setEnrollmentComplete] = useState(null);
  const [dataDeleted, setDataDeleted] = useState(false);

  async function handleDeleteData() {
    if (busy || dataDeleted) return;
    if (!window.confirm("Permanently delete all saved child profiles, chats, feedback, and privacy consent? Your login account will remain. This cannot be undone.")) return;
    setBusy(true); setMessage("");
    try {
      await deleteMyData();
      window.speechSynthesis?.cancel();
      setDataDeleted(true);
      onDataDeleted?.();
      setMessage("Your saved app data was deleted. Your account is still active. Review the privacy notice again before adding profiles or requesting guidance.");
    } catch (error) {
      onDataDeleted?.();
      setMessage(error.message || "Data deletion could not finish. Please try again.");
    } finally { setBusy(false); }
  }

  async function handleDeleteAccount() {
    if (busy) return;
    if (!window.confirm("Permanently delete your account, all child profiles, questions, answers, and feedback? This cannot be undone.")) return;
    setBusy(true);
    setMessage("");
    try {
      await deleteAccount();
      window.speechSynthesis?.cancel();
      await logout();
    } catch (error) {
      setMessage(error.message || "Account deletion could not finish. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  // ask firebase for current account details whenever this page opens.
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
      // Ignore the response if the page was removed while the request was pending.
      cancelled = true;
    };
  }, []);

  // count down before another resend; reloading resets this wait, not firebase's limits.
  useEffect(() => {
    if (resendSecondsLeft <= 0) return;
    const timerID = setTimeout(() => {
      setResendSecondsLeft((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    // cancel the old timer when replacing it or leaving the page.
    return () => clearTimeout(timerID);
  }, [resendSecondsLeft]);

  // check the email and authenticator status again when the user presses the button.
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

  // request another verification email unless an action or countdown is still running.
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

        // start the wait after firebase accepts the email request.
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

  // start setup; the authenticator is added only after a correct code is confirmed.
  async function handleBeginEnrollment() {
    if (busy) return;
    setBusy(true);
    setMessage("");
    setEnrollmentCode("");

    try {
      const pending = await beginTotpEnrollment();

      // this setup text contains the secret, so do not print or share it.
      const setupUri = pending.secret.generateQrCodeUrl(
        email,
        "Parenting Voice Assistant",
      );

      // make the qr image in this browser without sending the secret to another website.
      const qrDataUrl = await QRCode.toDataURL(setupUri, {
        width: 240,
        margin: 4,
      });

      // keep the key and qr together so cancel and completion can clear both.
      setPendingEnrollment({ ...pending, qrDataUrl });
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

  // check the code with firebase and remove setup details when the authenticator is added.
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

  // wait for the first account check before showing setup buttons.
  if (checkingStatus) {
    return <p className="account-initial-loading" role="status">Loading account…</p>;
  }

  return (
    <section className="account-page" aria-labelledby="account-page-title">
      <header className="account-page-heading">
        <p className="account-eyebrow">ACCOUNT SETTINGS</p>
        <h1 id="account-page-title">{emailVerified ? "Your account" : "Verify your email"}</h1>
        <p>Manage your sign-in security and saved information.</p>
      </header>
      <div className="account-identity-card">
        <span className="account-avatar" aria-hidden="true">{email?.charAt(0).toUpperCase() || "A"}</span>
        <div className="account-identity-details"><span className="account-field-label">Email address</span><p>{email}</p></div>
      {accountAccess && <p className={`account-status${accountAccess.verified ? " account-status--verified" : ""}`} role="status">
        {accountAccess.checking ? "Checking verification…" : accountAccess.verified ? "Verified" : accountAccess.error}
      </p>}
      </div>
      <section className="account-card" aria-labelledby="account-security-title">
        <div className="account-card-heading"><h2 id="account-security-title" className={enrollmentComplete === true ? "account-mfa-enabled" : undefined}>
          {enrollmentComplete === true && <svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="11" fill="currentColor" />
            <path d="m7 12 3 3 7-7" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>}
          {enrollmentComplete === true ? "MFA enabled" : enrollmentComplete === false ? "Set up MFA" : "MFA status unavailable"}
        </h2></div>
      {emailVerified ? (
        <div className="account-security-content">
          {!accountAccess?.verified && <p className="email-verified">Email verified.</p>}

          {/* show the saved authenticator status, the setup form, or the setup button. */}
          {enrollmentComplete ? (!accountAccess?.verified && (
            <p>
               Authenticator enrolled. Log out and sign in with your authenticator code to complete verification.
            </p>
          )) : pendingEnrollment ? (
            <form className="account-enrollment" onSubmit={handleConfirmEnrollment}>
              <p>
                Scan this QR code with your authenticator app, then enter its
                six-digit code below. If you cannot scan it, use the setup key
                instead.
              </p>
              <img
                src={pendingEnrollment.qrDataUrl}
                alt="QR code for setting up your authenticator"
                width={240}
                height={240}
              />
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
                  // clear the setup key, qr, and code when the user cancels.
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
        <div className="account-security-content">
          {/* After a reload, the previous email-request status may be unknown. */}
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
      </section>
      <p className="account-feedback" role="status">{message}</p>
      {accountAccess?.verified && <AccountUsage revision={dataDeleted} />}
      {accountAccess?.verified && <AccountConsent key={String(dataDeleted)} />}
      {accountAccess?.verified && <AdminFeedbackSummary />}
      {accountAccess?.verified && <section className="account-card account-data" aria-labelledby="account-data-title">
        <div className="account-card-heading"><h2 id="account-data-title">Data and account</h2>
          <p>These actions permanently remove information and cannot be undone.</p></div>
        <div className="account-data-row"><div><h3>Delete saved data</h3>
        <p>Remove all saved child profiles, chats, feedback, and privacy consent. Keep your login account.</p>
        </div>
        <button className="delete-action" type="button" disabled={busy || dataDeleted} onClick={handleDeleteData}>Delete my data</button>
        </div>
        <div className="account-data-row"><div><h3>Delete account</h3>
        <p>Permanently remove your account, child profiles, saved questions, answers, and feedback.</p>
        </div>
        <button className="delete-action" type="button" disabled={busy} onClick={handleDeleteAccount}>Delete my account</button>
        </div>
      </section>}
    </section>
  );
}

export default AccountPage;
