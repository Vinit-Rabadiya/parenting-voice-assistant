import { useEffect, useId, useState } from "react";
import { getFeedbackSummary } from "../services/caregiving";

const investigationCategories = new Map([
  ["Unclear", "unclear"],
  ["Repeated advice", "repeated_advice"],
  ["Did not answer the message", "did_not_answer"],
  ["Not suited to the child's age", "not_age_appropriate"],
]);

function validSummary(value) {
  return value?.unit === "Saved feedback per answer" && ["ratings", "reasons", "legacy_helpfulness"].every(key =>
    Array.isArray(value[key]) && value[key].every(item => typeof item?.label === "string" && item.label.trim()
      && Number.isSafeInteger(item.count) && item.count >= 0))
    && Number.isSafeInteger(value.comment_count) && value.comment_count >= 0
    && Array.isArray(value.comments) && value.comments.length <= 50 && value.comments.length <= value.comment_count
    && value.comments.every(item => typeof item?.comment === "string" && item.comment.trim() && item.comment.length <= 500
      && (item.rating === null || (Number.isInteger(item.rating) && item.rating >= 1 && item.rating <= 5))
      && (item.helpful === null || typeof item.helpful === "boolean")
      && Array.isArray(item.reasons) && item.reasons.length <= 4
      && item.reasons.every(reason => typeof reason === "string" && reason.trim() && reason.length <= 80));
}

export default function AdminFeedbackSummary({ onInvestigate, investigationDisabled }) {
  const [report, setReport] = useState({ status: "loading", summary: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timer = setTimeout(() => {
      controller.abort();
      if (active) setReport({ status: "error", summary: null, message: "Feedback took too long to load. Please try again." });
    }, 20000);
    async function load() {
      setReport({ status: "loading", summary: null });
      try {
        const summary = await getFeedbackSummary(controller.signal);
        if (!validSummary(summary)) throw new Error("Invalid grouped feedback response");
        if (active && !controller.signal.aborted) setReport({ status: "ready", summary });
      } catch (cause) {
        if (!active || controller.signal.aborted) return;
        const denied = cause.status === 401 || cause.status === 403;
        setReport({ status: denied ? "denied" : "error", summary: null,
          message: denied ? "Administrator access is unavailable. Sign out and sign in again."
            : "Feedback could not be loaded. Please try again." });
      } finally { clearTimeout(timer); }
    }
    void load();
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [attempt]);

  const loading = report.status === "loading";
  const summary = report.summary;
  const noFeedback = summary && [...summary.ratings, ...summary.reasons, ...summary.legacy_helpfulness]
    .every(item => item.count === 0);
  return <section className="admin-feedback" aria-label="Feedback overview" aria-busy={loading}>
    <header className="admin-report-toolbar">
      <h2>Caregiver feedback</h2>
      <button type="button" disabled={loading || report.status === "denied"} onClick={() => setAttempt(value => value + 1)}>
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 7v5h-5M4 17v-5h5" /><path d="M6.1 7a7 7 0 0 1 11.5-1L20 9M4 15l2.4 3A7 7 0 0 0 17.9 17" />
        </svg>Refresh feedback
      </button>
    </header>
    {loading && <><p className="admin-load-status" role="status">Loading feedback…</p>
      <div className="admin-report-grid" aria-hidden="true">{[0, 1].map(key => <div className="admin-panel admin-skeleton" key={key}>
        <span />{[0, 1, 2, 3].map(row => <div key={row}><span /><span /></div>)}
      </div>)}</div></>}
    {report.message && <div className="admin-state-card"><p role="alert">{report.message}</p>
      {report.status === "error" && <button type="button" onClick={() => setAttempt(value => value + 1)}>Try again</button>}
    </div>}
    {summary && <>
      {noFeedback && <div className="admin-empty-state" role="status">
        <span className="admin-empty-icon" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 5h14v11H9l-4 4z" /><path d="M9 9h6m-6 3h4" />
        </svg></span>
        <div><h2>No feedback yet</h2><p>Saved ratings and reasons will appear here.</p></div>
      </div>}
      <div className="admin-report-grid">
        <Buckets title="Helpfulness ratings" items={summary.ratings} ratings />
        <Buckets title="Feedback reasons" items={summary.reasons}
          onInvestigate={onInvestigate} investigationDisabled={investigationDisabled} />
      </div>
      {summary.legacy_helpfulness.some(item => item.count > 0) && <details className="admin-legacy">
        <summary>Earlier feedback</summary><Buckets title="Helpful / Not helpful" items={summary.legacy_helpfulness} />
      </details>}
      <p className="admin-report-note">Each answer's saved feedback counts once. Refresh to see new ratings and changes.</p>
      <section className="admin-panel admin-comments" aria-labelledby="admin-comments-title">
        <header className="admin-panel-heading"><h2 id="admin-comments-title">Written feedback</h2>
          <span className="admin-comment-count">{summary.comment_count} {summary.comment_count === 1 ? "comment" : "comments"}</span></header>
        {summary.comments.length === 0 ? <p>No written feedback has been shared yet.</p> : <>
          {summary.comment_count > summary.comments.length && <p className="admin-report-note">Showing the {summary.comments.length} most recent comments of {summary.comment_count}.</p>}
          <ul className="admin-comment-list" tabIndex="0" aria-label="Written feedback comments">{summary.comments.map((item, index) => <li key={index}>
            <div className="admin-comment-tags"><span>{item.rating !== null ? `Rating: ${item.rating} / 5` : item.helpful ? "Helpful" : "Not helpful"}</span>
              {item.reasons.map(reason => <span key={reason}>{reason}</span>)}</div>
            <p className="admin-comment-text">{item.comment}</p>
          </li>)}</ul>
        </>}
      </section>
    </>}
  </section>;
}

function Buckets({ title, items, ratings = false, onInvestigate, investigationDisabled }) {
  const heading = useId();
  return <section className="admin-panel" aria-labelledby={heading}>
    <header className="admin-panel-heading"><span className="admin-panel-icon" aria-hidden="true">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        {ratings ? <path d="M5 20V10m7 10V4m7 16v-7" /> : <><path d="M5 5h14v11H9l-4 4z" /><path d="M9 9h6m-6 3h4" /></>}
      </svg></span><h2 id={heading}>{title}</h2></header>
    <dl className="admin-band-list">{items.map(item => {
      const rating = ratings && /^([1-5])\s*[—-]\s*(.+)$/.exec(item.label);
      const category = investigationCategories.get(item.label);
      const canInvestigate = onInvestigate && category && item.count > 0;
      return <div className="admin-band-row" key={item.label}><dt>
        {rating && <span className="admin-rating-number">{rating[1]}</span>}<span>{rating ? rating[2] : item.label}</span>
      </dt><dd><span className="admin-band-count"><strong>{item.count}</strong>
        <span>{item.count === 1 ? "response" : "responses"}</span></span>
        {canInvestigate && <button type="button" disabled={investigationDisabled} aria-label={`Investigate: ${item.label}`}
          onClick={() => onInvestigate(category)}>Investigate</button>}</dd></div>;
    })}</dl>
  </section>;
}
