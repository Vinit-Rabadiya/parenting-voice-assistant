import { useEffect, useState } from "react";
import { getAdminTokenUsage } from "../services/caregiving";

const providers = { gemini: "Gemini", groq: "Groq" };
const columns = {
  input_tokens: "Input", output_tokens: "Output", thinking_tokens: "Thinking reported",
  total_tokens: "Total tokens", model_calls: "Calls recorded",
};
const number = new Intl.NumberFormat();
const date = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

function validCounts(counts) {
  return counts && Object.keys(columns).every(key => Number.isSafeInteger(counts[key]) && counts[key] >= 0);
}

function validUsage(value) {
  return validCounts(value?.total)
    && (value.first_recorded_at === null || (typeof value.first_recorded_at === "string"
      && Number.isFinite(Date.parse(value.first_recorded_at))))
    && Array.isArray(value.providers) && value.providers.length <= 2
    && value.providers.every(row => validCounts(row) && Object.hasOwn(providers, row.provider))
    && new Set(value.providers.map(row => row.provider)).size === value.providers.length;
}

export default function AdminTokenUsage() {
  const [report, setReport] = useState({ loading: true });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => {
      controller.abort();
      setReport({ error: true });
    }, 15000);
    async function load() {
      try {
        const usage = await getAdminTokenUsage(controller.signal);
        if (!validUsage(usage)) throw new Error("Invalid token usage report");
        if (!controller.signal.aborted) setReport({ usage });
      } catch (error) {
        if (!controller.signal.aborted) setReport({ error: true, denied: error?.status === 401 || error?.status === 403 });
      } finally {
        clearTimeout(timeout);
      }
    }
    void load();
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [attempt]);

  const usage = report.usage;
  return <section className="admin-panel admin-token-usage" aria-labelledby="admin-token-usage-title" aria-busy={Boolean(report.loading)}>
    <header className="admin-report-toolbar">
      <h2 id="admin-token-usage-title">Model token usage</h2>
      <button type="button" disabled={report.loading || report.denied} onClick={() => {
        setReport({ loading: true });
        setAttempt(value => value + 1);
      }}>Refresh usage</button>
    </header>
    {report.loading && <p role="status">Loading token usage…</p>}
    {report.error && <p role="alert">{report.denied ? "Administrator access is required to view token usage."
      : "Token usage could not be loaded. Refresh usage to try again."}</p>}
    {usage && (usage.first_recorded_at === null
      ? <p>No model token usage has been recorded yet.</p>
      : <>
        <p className="admin-report-note">Provider-reported tokens recorded since {date.format(new Date(usage.first_recorded_at))}.</p>
        <div className="admin-usage-table" role="region" aria-label="Token usage by provider" tabIndex={0}>
          <table>
            <thead><tr><th scope="col">Provider</th>{Object.entries(columns).map(([key, label]) => <th key={key} scope="col">{label}</th>)}</tr></thead>
            <tbody>{usage.providers.map(row => <tr key={row.provider}>
              <th scope="row">{providers[row.provider]}</th>
              {Object.keys(columns).map(key => <td key={key}>{number.format(row[key])}</td>)}
            </tr>)}</tbody>
            <tfoot><tr><th scope="row">Overall</th>
              {Object.keys(columns).map(key => <td key={key}>{number.format(usage.total[key])}</td>)}
            </tr></tfoot>
          </table>
        </div>
      </>)}
  </section>;
}
