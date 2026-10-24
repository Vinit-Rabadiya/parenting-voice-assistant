import { useEffect, useRef, useState } from "react";
import { getFeedbackAdminAccess, getFeedbackSummary } from "../services/caregiving";

export default function AdminFeedbackSummary() {
  const [allowed, setAllowed] = useState(false);
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const dialogRef = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    async function check() {
      try {
        const access = await getFeedbackAdminAccess(controller.signal);
        if (!controller.signal.aborted) setAllowed(access.allowed === true);
      } catch {
        if (!controller.signal.aborted) setAllowed(false);
      }
    }
    check();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!allowed || !open) return;
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
      document.body.style.overflow = previousOverflow;
    };
  }, [allowed, open]);

  useEffect(() => {
    if (!allowed || !open) return;
    const controller = new AbortController();
    async function load() {
      setLoading(true); setResult(null); setError("");
      try {
        const summary = await getFeedbackSummary(controller.signal);
        if (!controller.signal.aborted) setResult(summary);
      } catch (cause) {
        if (controller.signal.aborted) return;
        if (cause.status === 401 || cause.status === 403) {
          setResult(null); setOpen(false); setAllowed(false);
        } else setError("Feedback summary could not be loaded. Please try again.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [allowed, open, attempt]);

  function close() { setOpen(false); setResult(null); setError(""); }
  if (!allowed) return null;
  return <section className="account-card" aria-labelledby="feedback-summary-title">
    <div className="account-card-heading"><h2 id="feedback-summary-title">Feedback overview</h2>
      <p>Administrator access to grouped feedback only. Private chats are not available here.</p></div>
    <button type="button" aria-haspopup="dialog" onClick={() => setOpen(true)}>View feedback overview</button>
    {open && <dialog ref={dialogRef} className="account-consent-dialog" aria-labelledby="feedback-dialog-title"
      onCancel={close} onClose={close}>
      <header className="account-consent-dialog-heading"><h2 id="feedback-dialog-title">Grouped feedback</h2>
        <button type="button" autoFocus onClick={close}>Close</button></header>
      <div aria-busy={loading}>
        <p>Only the latest eligible feedback from each caregiver is counted. Counts are shown in bands of five;
          groups with fewer than five caregivers are hidden. No totals or individual records are shown.</p>
        {loading && <p role="status">Loading grouped feedback…</p>}
        {error && <><p role="alert">{error}</p>
          <button type="button" onClick={() => setAttempt(value => value + 1)}>Retry summary</button></>}
        {result && <>
          <Buckets title="Helpfulness ratings" items={result.ratings} />
          <Buckets title="Optional feedback reasons" items={result.reasons} />
          <Buckets title="Helpful / Not helpful feedback" items={result.legacy_helpfulness} />
          <p>The two rating scales are kept separate. Ratings do not establish medical accuracy.</p>
        </>}
      </div>
    </dialog>}
  </section>;
}

function Buckets({ title, items }) {
  return <section><h3>{title}</h3><dl>{items.map(item =>
    <div className="account-data-row" key={item.label}><dt>{item.label}</dt>
      <dd>{item.lower === null ? "Not enough grouped feedback" : `${item.lower}–${item.upper} caregivers`}</dd>
    </div>)}</dl></section>;
}
