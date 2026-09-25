import { useState } from "react";
function VerifyEmailPage({ verificationEmailRequested }) {
    const[busy,setBusy]=useState(false);

  return (
    <section>
      <h1>Verify your email.</h1>

      {verificationEmailRequested ? (
        <p>Check your inbox and spam folder for the verification link.</p>
      ) : (
        <p>Account created, but we couldn’t send the verification email.</p>
      )}

      <button type="button" disabled={busy}>Check Verification Status</button>
    </section>
  );
}

export default VerifyEmailPage;
