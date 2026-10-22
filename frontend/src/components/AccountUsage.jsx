import { useEffect, useRef, useState } from "react";
import { getAccountUsage } from "../services/caregiving";

export default function AccountUsage({ revision = false }) {
  const [open, setOpen] = useState(false);
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
  return <section className="account-card" aria-labelledby="account-usage-title">
    <div className="account-card-heading"><h2 id="account-usage-title">Usage</h2>
      <p>Check your request counts and remaining allowances.</p></div>
    <button type="button" aria-haspopup="dialog" onClick={() => setOpen(true)}>View usage</button>
    {open && <dialog ref={dialogRef} className="account-consent-dialog" aria-labelledby="usage-dialog-title"
      onCancel={() => setOpen(false)} onClose={() => setOpen(false)}>
      <header className="account-consent-dialog-heading"><h2 id="usage-dialog-title">Your usage</h2>
        <button type="button" autoFocus onClick={() => setOpen(false)}>Close</button></header>
      <UsageDetails revision={revision} />
    </dialog>}
  </section>;
}

function UsageDetails({ revision }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");
      setResult(null);
      try {
        const usage = await getAccountUsage(controller.signal);
        if (!controller.signal.aborted) setResult(usage);
      } catch {
        if (!controller.signal.aborted) setError("Usage could not be loaded. Please try again.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [refresh, revision]);

  const date = (value) => new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  return <div aria-busy={loading}>
    <p>Your current request allowances. Reset times are shown in your local time.</p>
    {loading && <p role="status">Loading usage…</p>}
    {error && <p role="alert">{error}</p>}
    {result?.items.map((item) => <div className="account-data-row" key={item.action}>
      <div><h3>{item.action === "coaching" ? "Coaching requests" : "New child profiles"}</h3>
        <p>{item.hourly.used} of {item.hourly.limit} this hour · {item.hourly.remaining} remaining</p>
        <p><small>Hourly reset: {date(item.hourly.resets_at)}</small></p>
        <p>{item.daily.used} of {item.daily.limit} today · {item.daily.remaining} remaining</p>
        <p><small>Daily reset: {date(item.daily.resets_at)}</small></p>
      </div></div>)}
    {result && <p><small>Updated {date(result.as_of)}. Accepted attempts count even if no guidance is generated.</small></p>}
    <button type="button" disabled={loading} onClick={() => setRefresh((value) => value + 1)}>Refresh usage</button>
  </div>;
}
