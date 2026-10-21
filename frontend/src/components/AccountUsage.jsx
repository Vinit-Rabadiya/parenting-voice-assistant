import { useEffect, useState } from "react";
import { getAccountUsage } from "../services/caregiving";

export default function AccountUsage({ revision = false }) {
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
  return <section className="account-card" aria-labelledby="account-usage-title" aria-busy={loading}>
    <div className="account-card-heading"><h2 id="account-usage-title">Usage</h2>
      <p>Your current request allowances. Reset times are shown in your local time.</p></div>
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
  </section>;
}
