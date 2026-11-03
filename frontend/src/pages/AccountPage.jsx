// this page manages email verification, qr authenticator setup, backend checks, and logout.
// app.jsx opens this page for account management or signed-in onboarding.
import { useState, useEffect, useRef } from "react";
import { saveChildSelection } from "../services/childSelection";
import { resendVerificationEmail } from "../services/auth";
import { useAuth } from "../hooks/useAuth";
import {
  beginTotpEnrollment,
  confirmTotpEnrollment,
  getAccountSecurityStatus,
  reauthenticateAccount,
  completeTotpSignIn,
  totpSignInFactors,
  turnOffMfa,
} from "../services/auth";
import AccountUsage from "../components/AccountUsage";
import AccountConsent from "../components/AccountConsent";
import { deleteAccount, deleteMyData } from "../services/caregiving";
import { stopGuidanceAudio } from "../hooks/useGuidanceAudio";
import usePlaybackPreference, { clearPlaybackPreference } from "../hooks/usePlaybackPreference";

function securityErrorMessage(error, stage) {
  const messages = {
    "auth/requires-recent-login": "Confirm your sign-in again before changing an authenticator.",
    "auth/invalid-multi-factor-session": "Authenticator setup expired. Confirm your sign-in and start setup again.",
    "auth/missing-multi-factor-session": "Authenticator setup needs a new sign-in confirmation. Please try again.",
    "auth/user-token-expired": "Your sign-in expired. Sign out and sign in again before continuing.",
    "app/login-required": "Sign in before setting up an authenticator.",
    "app/account-changed": "The signed-in account changed. Reopen My Account and start again.",
    "auth/unverified-email": "Verify your email before adding an authenticator.",
    "app/authenticator-limit": "Two authenticators are already set up. Refresh My Account to see the current status.",
    "auth/maximum-second-factor-count-exceeded": "The authenticator limit has been reached. Refresh My Account to check the current status.",
    "auth/second-factor-already-in-use": "This authenticator is already set up. Refresh My Account to check its status.",
    "auth/network-request-failed": "Could not connect. Check your internet connection and try again.",
    "auth/too-many-requests": "Too many attempts. Wait a few minutes before trying again.",
    "auth/operation-not-allowed": "Authenticator setup is unavailable. Contact the account administrator to check the sign-in configuration.",
    "auth/unsupported-first-factor": "Sign in again with Google or email and password before adding an authenticator.",
    "auth/popup-blocked": "Allow the Google sign-in popup, then select Continue with Google again.",
    "auth/popup-closed-by-user": "Sign-in confirmation was cancelled. Select Continue with Google to try again.",
    "auth/invalid-verification-code": "The authenticator code was not accepted. Enter the current six-digit code and check that your device time is automatic.",
    "auth/code-expired": "That code expired. Enter the current code from your authenticator app.",
    "auth/wrong-password": "The password was not accepted. Check it and try again.",
    "auth/invalid-credential": "Sign-in could not be confirmed. Check your sign-in details and try again.",
  };
  if (Object.hasOwn(messages, error?.code)) return messages[error.code];
  if (error?.status === 403) return "This security change is not allowed. Refresh My Account to check your account policy.";
  if (error?.status === 503) return "Account security is temporarily unavailable. Please try again later.";
  return stage === "setup" ? "Authenticator setup could not finish. Try again or contact the account administrator."
    : "Sign-in could not be confirmed. Check your details and try again.";
}

function setupSessionExpired(error) {
  return ["auth/requires-recent-login", "auth/invalid-multi-factor-session", "auth/missing-multi-factor-session"].includes(error?.code);
}

function AccountPage({ verificationEmailRequested, email, accountAccess, onDataDeleted }) {
  const administrator = accountAccess?.role === "administrator";
  const { logout, user } = useAuth();
  const { automatic, setAutomatic } = usePlaybackPreference(user?.uid);
  const [playbackMessage, setPlaybackMessage] = useState("");
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
  const [mfaRequired, setMfaRequired] = useState(false);
  const [factorCount, setFactorCount] = useState(0);
  const [usesGoogle, setUsesGoogle] = useState(false);
  const [securityAction, setSecurityAction] = useState(null);
  const [securityPassword, setSecurityPassword] = useState("");
  const [securityCode, setSecurityCode] = useState("");
  const [securityFactor, setSecurityFactor] = useState("");
  const [dataDeleted, setDataDeleted] = useState(false);
  const [securityErrorCode, setSecurityErrorCode] = useState("");
  const setupAttempt = useRef(0);
  useEffect(() => () => { setupAttempt.current += 1; }, []);

  function reportSecurityError(error, stage) {
    setMessage(securityErrorMessage(error, stage));
    if (error?.code === "app/authenticator-limit") setFactorCount(2);
    // A short code helps support identify provider failures without exposing the
    // exception message, setup key, request body or authentication credentials.
    setSecurityErrorCode(typeof error?.code === "string" && /^auth\/[a-z-]{1,60}$/.test(error.code) ? error.code : "");
  }

  async function handleDeleteData() {
    if (busy || dataDeleted) return;
    if (!window.confirm(administrator
      ? "Permanently delete personal application data saved on this account? Your login and administrator role will remain. This cannot be undone."
      : "Permanently delete all saved child profiles, chats, feedback, and privacy consent? Your login account will remain. This cannot be undone.")) return;
    setBusy(true); setMessage("");
    try {
      await deleteMyData();
      clearPlaybackPreference(user?.uid);
      stopGuidanceAudio();
      setDataDeleted(true);
      onDataDeleted?.();
      setMessage(administrator ? "Your personal application data was deleted. Your login and administrator role remain active."
        : "Your saved app data was deleted. Your account is still active. Review the privacy notice again before adding profiles or requesting guidance.");
    } catch (error) {
      onDataDeleted?.();
      setMessage(error.message || "Data deletion could not finish. Please try again.");
    } finally { setBusy(false); }
  }

  async function handleDeleteAccount() {
    if (busy) return;
    if (!window.confirm(administrator ? "Permanently delete your account and its personal application data? This cannot be undone."
      : "Permanently delete your account, all child profiles, questions, answers, and feedback? This cannot be undone.")) return;
    setBusy(true);
    setMessage("");
    try {
      await deleteAccount();
      clearPlaybackPreference(user?.uid);
      saveChildSelection(user.uid, null);
      stopGuidanceAudio();
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
          setMfaRequired(status.mfaRequired === true);
          setFactorCount(status.factorCount || 0);
          setUsesGoogle(status.usesGoogle === true);
        }
      } catch {
        if (!cancelled) {
          setMessage(
            "Couldn’t check account security. Please try again.",
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
      const status = await getAccountSecurityStatus({ refresh: true });
      const isVerified = status.emailVerified;

      setEmailVerified(isVerified);
      setEnrollmentComplete(status.totpEnrolled);
      setMfaRequired(status.mfaRequired === true);
      setFactorCount(status.factorCount || 0);
      setUsesGoogle(status.usesGoogle === true);
      window.dispatchEvent(new Event("account-security-changed"));
      if (isVerified === true) {
        setMessage(
          status.totpEnrolled
            ? "Email verified. Authenticator is enrolled."
            : "Email verified. You can continue; MFA is optional unless required by security policy.",
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

  async function createEnrollment() {
    const attempt = ++setupAttempt.current;
    const pending = await beginTotpEnrollment();
    if (attempt !== setupAttempt.current) return;
    let qrDataUrl = null;
    try {
      const setupUri = pending.secret.generateQrCodeUrl(email, "Parenting Voice Assistant");
      const { default: QRCode } = await import("qrcode");
      qrDataUrl = await QRCode.toDataURL(setupUri, { width: 240, margin: 4 });
    } catch { /* Manual setup with the same secret remains available. */ }
    if (attempt !== setupAttempt.current) return;
    setPendingEnrollment({ ...pending, qrDataUrl });
    if (!qrDataUrl) setMessage("The QR code could not be displayed. Use the setup key below in your authenticator app instead.");
  }

  async function handleReauthentication(event) {
    event.preventDefault();
    if (busy || !securityAction) return;
    setBusy(true); setMessage(""); setSecurityErrorCode("");
    let stage = "sign-in";
    try {
      if (securityAction.resolver) {
        const confirmed = await completeTotpSignIn(securityAction.resolver, securityCode, securityFactor || null);
        if (confirmed.uid !== user.uid) throw new Error("Account changed. Please sign in again.");
      } else {
        const result = await reauthenticateAccount(securityPassword, user.uid);
        if (result.next === "mfa-required") {
          setSecurityAction({ ...securityAction, resolver: result.resolver });
          return;
        }
      }
      if (securityAction.intent === "disable") {
        await turnOffMfa(user.uid);
        await logout();
      } else if (securityAction.intent === "enroll") {
        stage = "setup";
        await createEnrollment();
      }
      setSecurityAction(null);
      setSecurityFactor("");
      if (securityAction.intent === "access") window.dispatchEvent(new Event("account-security-changed"));
    } catch (error) {
      reportSecurityError(error, stage);
      if (setupSessionExpired(error)) {
        setPendingEnrollment(null); setSecurityFactor("");
        setSecurityAction({ intent: securityAction.intent });
      } else if (stage === "setup") setSecurityAction(null);
    } finally {
      setSecurityPassword(""); setSecurityCode(""); setBusy(false);
    }
  }

  // Enrollment is complete only after Firebase verifies the authenticator code.
  function handleBeginEnrollment() {
    if (busy) return;
    setMessage("Confirm your sign-in before adding an authenticator.");
    setSecurityErrorCode("");
    setEnrollmentCode("");
    setSecurityAction({ intent: "enroll" });
  }

  // check the code with firebase and remove setup details when the authenticator is added.
  async function handleConfirmEnrollment(event) {
    event.preventDefault();
    if (busy || !pendingEnrollment) return;

    setBusy(true);
    setMessage(""); setSecurityErrorCode("");

    try {
      await confirmTotpEnrollment(pendingEnrollment, enrollmentCode);
      setPendingEnrollment(null);
      setEnrollmentComplete(true);
      setFactorCount((count) => count + 1);
      window.dispatchEvent(new Event("account-security-changed"));
      setMessage(
        "Authenticator added. If prompted, confirm sign-in with your code to continue.",
      );
    } catch (error) {
      reportSecurityError(error, "setup");
      if (setupSessionExpired(error)) { setPendingEnrollment(null); setSecurityAction({ intent: "enroll" }); }
    } finally {
      setEnrollmentCode("");
      setBusy(false);
    }
  }

  return (
    <section className="account-page" aria-labelledby="account-page-title">
      <header className="account-page-heading">
        <p className="account-eyebrow">ACCOUNT SETTINGS</p>
        <h1 id="account-page-title">{emailVerified === false ? "Verify your email" : "Your account"}</h1>
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
          {enrollmentComplete === true ? "MFA enabled" : enrollmentComplete === false ? (mfaRequired ? "MFA required" : "MFA off") : checkingStatus ? "MFA" : "MFA status unavailable"}
        </h2></div>
      {checkingStatus ? <p role="status">Loading security settings...</p> : emailVerified === null ? null : emailVerified ? (
        <div className="account-security-content">
          {!accountAccess?.verified && <p className="email-verified">Email verified.</p>}

          {/* show the saved authenticator status, the setup form, or the setup button. */}
          <p>{mfaRequired ? "MFA is required by security policy and cannot be turned off."
            : enrollmentComplete ? "Your authenticator protects sign-in with a six-digit code. You can keep MFA on or turn it off."
              : "MFA is off. You can add an authenticator for extra sign-in protection."}</p>
          {enrollmentComplete && <>
            {!accountAccess?.verified && <button type="button" disabled={busy || Boolean(securityAction)}
              onClick={() => setSecurityAction({ intent: "access" })}>Confirm sign-in</button>}
            {!pendingEnrollment && factorCount < 2 && <button type="button" disabled={busy || Boolean(securityAction)}
              onClick={handleBeginEnrollment}>Add backup authenticator</button>}
            <button type="button" className="delete-action" disabled={busy || mfaRequired || Boolean(securityAction) || Boolean(pendingEnrollment)}
              onClick={() => { setSecurityAction({ intent: "disable" }); setMessage(""); setSecurityErrorCode(""); }}>Turn off MFA</button>
            <p>{factorCount < 2 ? "A backup authenticator lets you sign in if you lose your main one. Set it up on another device."
              : "Two authenticators are set up. Keep your backup on a separate device."}</p>
            <p>If you lose access to all your authenticators, contact the account administrator for recovery.
              Changing your password does not remove MFA.</p>
          </>}
          {pendingEnrollment ? (
            <form className="account-enrollment" onSubmit={handleConfirmEnrollment}>
              <p>
                {pendingEnrollment.qrDataUrl
                  ? "Scan this QR code with your authenticator app, then enter its six-digit code below. You can also use the setup key instead."
                  : "Add this account manually in your authenticator app using the setup key below, then enter the six-digit code it generates."}
              </p>
              {pendingEnrollment.qrDataUrl && <img
                src={pendingEnrollment.qrDataUrl}
                alt="QR code for setting up your authenticator"
                width={240}
                height={240}
              />}
              <p>Setup key:</p>
              <code>{pendingEnrollment.secret.secretKey}</code>

              <p>Keep this setup key private and keep access to your authenticator.</p>

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
                  setupAttempt.current += 1;
                  setEnrollmentCode("");
                  setMessage(""); setSecurityErrorCode("");
                }}
              >
                Cancel setup
              </button>
            </form>
          ) : !enrollmentComplete && (
            <button
              type="button"
              disabled={busy || Boolean(securityAction)}
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
      {securityAction && <form className="account-enrollment" onSubmit={handleReauthentication}>
        <h3>Confirm your sign-in</h3>
        {securityAction.intent === "disable" && <p>Turning off MFA signs you out of existing sessions. Sign in again after the change.</p>}
        {securityAction.resolver ? <>
          {totpSignInFactors(securityAction.resolver).length > 1 && <label>Authenticator
            <select value={securityFactor || totpSignInFactors(securityAction.resolver)[0].uid}
              onChange={(event) => setSecurityFactor(event.target.value)} disabled={busy}>
              {totpSignInFactors(securityAction.resolver).map((factor, index) => <option key={factor.uid} value={factor.uid}>
                {factor.displayName || `Authenticator ${index + 1}`}</option>)}
            </select>
          </label>}
          <label>Authenticator code<input value={securityCode} onChange={(event) => setSecurityCode(event.target.value)}
            inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required disabled={busy} /></label>
        </> : !usesGoogle && <label>Current password<input type="password" autoComplete="current-password"
          value={securityPassword} onChange={(event) => setSecurityPassword(event.target.value)} required disabled={busy} /></label>}
        <button type="submit" disabled={busy}>{securityAction.resolver ? "Verify code" : usesGoogle ? "Continue with Google" : "Confirm sign-in"}</button>
        <button type="button" disabled={busy} onClick={() => {
          setSecurityAction(null); setSecurityPassword(""); setSecurityCode(""); setSecurityFactor(""); setMessage(""); setSecurityErrorCode("");
        }}>Cancel</button>
      </form>}
      </section>
      <p className="account-feedback" role="status">{message}</p>
      {securityErrorCode && <details className="account-feedback"><summary>Error reference</summary><code>{securityErrorCode}</code></details>}
      {accountAccess?.verified && !administrator && <section className="account-playback" aria-label="Spoken replies">
        <label className="account-playback-setting">
          <span>Read replies automatically</span>
          <input type="checkbox" role="switch" checked={automatic} onChange={(event) => {
            const saved = setAutomatic(event.target.checked);
            setPlaybackMessage(saved ? "" : "Your choice applies to this tab. This browser could not save it for future visits.");
          }} />
        </label>
        {playbackMessage && <p role="status">{playbackMessage}</p>}
      </section>}
      {accountAccess?.verified && !administrator && <AccountUsage revision={dataDeleted} />}
      {accountAccess?.verified && !administrator && <AccountConsent key={String(dataDeleted)} />}
      {accountAccess?.verified && <section className="account-card account-data" aria-labelledby="account-data-title">
        <div className="account-card-heading"><h2 id="account-data-title">Data and account</h2>
          <p>These actions permanently remove information and cannot be undone.</p></div>
        <div className="account-data-row"><div><h3>Delete saved data</h3>
        <p>{administrator ? "Remove personal application data retained from earlier use. Keep your login and administrator role."
          : "Remove all saved child profiles, chats, feedback, and privacy consent. Keep your login account."}</p>
        </div>
        <button className="delete-action" type="button" disabled={busy || dataDeleted} onClick={handleDeleteData}>Delete my data</button>
        </div>
        <div className="account-data-row"><div><h3>Delete account</h3>
        <p>{administrator ? "Permanently remove your account and its personal application data."
          : "Permanently remove your account, child profiles, saved questions, answers, and feedback."}</p>
        </div>
        <button className="delete-action" type="button" disabled={busy} onClick={handleDeleteAccount}>Delete my account</button>
        </div>
      </section>}
    </section>
  );
}

export default AccountPage;
