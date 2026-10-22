import { useEffect, useRef, useState } from "react";
import { getPrivacyConsent } from "../services/caregiving";

export default function AccountConsent() {
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const dialogRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let active = true;
    const timer = setTimeout(() => {
      controller.abort();
      if (active) setError("Consent details took too long to load. Please retry.");
    }, 8000);
    getPrivacyConsent(controller.signal).then((value) => {
      if (!active || controller.signal.aborted) return;
      if (!Array.isArray(value?.notice) || typeof value.accepted !== "boolean" || typeof value.version !== "string") {
        throw new Error("Invalid consent details.");
      }
      setNotice(value);
    }).catch(() => {
      if (active && !controller.signal.aborted) setError("Consent details could not be loaded. Please retry.");
    }).finally(() => clearTimeout(timer));
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [open, attempt]);

  return <section className="account-card" aria-labelledby="account-consent-title">
    <div className="account-card-heading"><h2 id="account-consent-title">Privacy consent</h2>
      <p>Review the information covered by your consent.</p></div>
    <button type="button" aria-haspopup="dialog" onClick={() => {
      setNotice(null); setError(""); setOpen(true);
    }}>
      View accepted consent
    </button>
    {open && <dialog ref={dialogRef} className="account-consent-dialog" aria-labelledby="consent-dialog-title"
      onCancel={() => setOpen(false)} onClose={() => setOpen(false)}>
      <header className="account-consent-dialog-heading"><h2 id="consent-dialog-title">Your privacy consent</h2>
        <button type="button" autoFocus onClick={() => setOpen(false)}>Close</button></header>
      {!notice && !error && <p role="status">Loading consent details…</p>}
      {error && <><p role="alert">{error}</p><button type="button" onClick={() => { setError(""); setAttempt((value) => value + 1); }}>Retry consent details</button></>}
      {notice && <>
        <p role="status">{notice.accepted ? "You have accepted this privacy notice." : "You have not accepted the current privacy notice. Earlier versions are not available in this view."}</p>
        {notice.accepted && notice.accepted_at && <p>Accepted on {new Date(notice.accepted_at).toLocaleString()}</p>}
        <p>Notice version: {notice.version}</p>
        <ul>{notice.notice.map((item) => <li key={item}>{item}</li>)}</ul>
        {notice.accepted && <p>You confirmed that you are the parent or guardian, or are authorised to provide the child's information, and agreed to the use of your information and your child's information as explained in this notice.</p>}
      </>}
    </dialog>}
  </section>;
}
