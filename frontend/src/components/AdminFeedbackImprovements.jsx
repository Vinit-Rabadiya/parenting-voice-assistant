import { useEffect, useImperativeHandle, useRef, useState } from "react";
import {
  createFeedbackImprovement, deleteFeedbackImprovement, listFeedbackImprovements, updateFeedbackImprovement,
} from "../services/caregiving";
import "./AdminFeedbackImprovements.css";

const categories = { unclear: "Unclear", repeated_advice: "Repeated advice", did_not_answer: "Did not answer",
  not_age_appropriate: "Not age appropriate", other: "Other concern" };
const stages = { investigating: "Investigating", ready_for_release: "Evaluation recorded", released: "Release recorded" };
const panels = { concern: "Concern", evaluation: "Test a fix", release: "Release record" };
const dimensions = { faithfulness: "Source support", helpfulness: "Helpfulness", age_fit: "Age fit", clarity: "Clarity", safety: "Safety boundaries" };
const checkLabels = { issue_resolved: "The reproduced issue was resolved", sources_checked: "Source support was checked",
  age_checked: "Age conditions were checked", safety_checked: "Safety boundaries were checked", regressions_passed: "Regression checks passed" };
const captureFields = { model: "Actual model", prompt_revision: "Prompt revision", corpus_revision: "Corpus revision", report_reference: "Evaluation report reference" };
const blankReview = () => ({ answer: "", model: "", prompt_revision: "", corpus_revision: "", report_reference: "",
  faithfulness_not_applicable: false, faithfulness_note: "",
  scores: Object.fromEntries(Object.keys(dimensions).map(key => [key, null])) });
const newContent = (category = "unclear") => ({ title: "", category, scenario: "", expected_behavior: "",
  fictional_confirmed: false, status: "investigating",
  change_area: "prompt", change_summary: "", change_reference: "",
  baseline: blankReview(), candidate: blankReview(), checks: Object.fromEntries(Object.keys(checkLabels).map(key => [key, false])),
  evaluation_notes: "", release_revision: "", deployment_checked: false, release_notes: "" });

function validRecord(record) {
  const content = record?.content;
  return /^[0-9a-f]{32}$/.test(record?.id) && Number.isSafeInteger(record.version) && record.version > 0
    && content && Object.hasOwn(stages, content.status) && Object.hasOwn(categories, content.category)
    && ["title", "scenario", "expected_behavior", "change_area", "change_summary",
      "change_reference", "evaluation_notes", "release_revision", "release_notes"].every(key => typeof content[key] === "string")
    && ["fictional_date_of_birth", "evaluation_date"].every(key => content[key] == null || typeof content[key] === "string")
    && typeof content.fictional_confirmed === "boolean" && typeof content.deployment_checked === "boolean"
    && ["baseline", "candidate"].every(side => content[side]
      && typeof content[side].faithfulness_not_applicable === "boolean" && typeof content[side].faithfulness_note === "string"
      && ["answer", ...Object.keys(captureFields)].every(key => typeof content[side][key] === "string")
      && Object.keys(dimensions).every(key => content[side].scores?.[key] === null
        || (Number.isInteger(content[side].scores?.[key]) && content[side].scores[key] >= 1 && content[side].scores[key] <= 5)))
    && Object.keys(checkLabels).every(key => typeof content.checks?.[key] === "boolean");
}

function evaluationProblem(content) {
  for (const side of ["baseline", "candidate"]) {
    if (!["answer", ...Object.keys(captureFields)].every(key => content[side][key].trim())
      || !Object.keys(dimensions).every(key => key === "faithfulness" && content[side].faithfulness_not_applicable
        ? content[side].scores[key] === null && content[side].faithfulness_note.trim() : Number.isInteger(content[side].scores[key]))) {
      return "Complete both answers, their run details and all review scores before recording evaluation.";
    }
  }
  if (!content.change_summary.trim() || !content.change_reference.trim() || !content.evaluation_notes.trim()
    || !Object.keys(checkLabels).every(key => content.checks[key])) {
    return "Record the correction, evidence, evaluation notes and all checks before advancing.";
  }
  if (["faithfulness", "age_fit", "safety"].some(key => content.candidate.scores[key] !== null
    && content.baseline.scores[key] !== null && content.candidate.scores[key] < content.baseline.scores[key])) {
    return "Resolve source-support, age-fit or safety-score regressions before advancing.";
  }
  if (["faithfulness", "age_fit", "safety"].some(key => content.candidate.scores[key] !== null && content.candidate.scores[key] < 4)) {
    return "Candidate source-support, age-fit and safety scores must be at least 4 / 5 when applicable.";
  }
  return "";
}

export default function AdminFeedbackImprovements({ ref, onInvestigationDisabledChange }) {
  const [page, setPage] = useState({ items: [], next_cursor: null });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  const [cursor, setCursor] = useState(null);
  const [selected, setSelected] = useState(null);
  const [content, setContent] = useState(null);
  const [panel, setPanel] = useState("concern");
  const mutation = useRef(null);
  const editorHeading = useRef(null);
  const editorAlert = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timer = setTimeout(() => {
      controller.abort();
      if (active) {
        setLoading(false); setPage({ items: [], next_cursor: null });
        setError("Improvement cases took too long to load. Please retry.");
      }
    }, 20000);
    listFeedbackImprovements(controller.signal, cursor).then(result => {
      if (!active || controller.signal.aborted) return;
      if (!Array.isArray(result?.items) || result.items.length > 50 || !result.items.every(validRecord)
        || !(result.next_cursor === null || /^[0-9a-f]{32}$/.test(result.next_cursor))) throw new Error("Invalid review cases");
      setPage(result); setLoading(false);
    }).catch(cause => {
      if (!active || controller.signal.aborted) return;
      setPage({ items: [], next_cursor: null }); setLoading(false);
      const refused = cause.status === 401 || cause.status === 403;
      setDenied(refused);
      if (refused) { setSelected(null); setContent(null); }
      setError(refused ? "Administrator access is unavailable. Sign in again." : "Improvement cases could not be loaded. Please retry.");
    }).finally(() => clearTimeout(timer));
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [reload, cursor]);

  useEffect(() => () => { mutation.current?.abort(); mutation.current = null; }, []);

  const editing = content !== null;
  const selectedId = selected?.id;
  useEffect(() => {
    if (editing) editorHeading.current?.focus();
  }, [editing, selectedId]);
  useEffect(() => {
    if (error && editing) editorAlert.current?.focus();
  }, [editing, error]);

  function refresh(nextCursor = null) {
    setError(""); setLoading(true); setCursor(nextCursor); setReload(value => value + 1);
  }

  function canDiscard() {
    return !content || (selected && JSON.stringify(content) === JSON.stringify(selected.content))
      || window.confirm("Discard unsaved review changes?");
  }

  function edit(record = null, category) {
    if (!canDiscard()) return;
    setSelected(record); setContent(record ? structuredClone(record.content) : newContent(category));
    setPanel(record && record.content.status !== "investigating" ? "release" : "concern");
    setError(""); setNotice("");
    if (editing && selectedId === record?.id) editorHeading.current?.focus();
  }

  useImperativeHandle(ref, () => ({
    startInvestigation(category) {
      if (!busy && !denied) edit(null, category);
    },
  }));
  useEffect(() => {
    onInvestigationDisabledChange?.(busy || denied);
  }, [busy, denied, onInvestigationDisabledChange]);

  const set = (key, value) => setContent(previous => ({ ...previous, [key]: value }));
  const setReview = (side, key, value) => setContent(previous => ({ ...previous, [side]: { ...previous[side], [key]: value } }));

  async function save(status) {
    setError(""); setNotice("");
    if (status !== "investigating") {
      const problem = evaluationProblem(content);
      if (problem) { setError(problem); return; }
    }
    if (status === "released" && (!/^[0-9a-f]{40}$/.test(content.release_revision) || !content.deployment_checked || !content.release_notes.trim())) {
      setError("Record the full 40-character deployed commit, deployment confirmation and release notes."); return;
    }
    const controller = new AbortController(); mutation.current = controller;
    const timer = setTimeout(() => {
      controller.abort();
      if (mutation.current === controller) {
        mutation.current = null; setBusy(false);
        setError("Saving timed out. Refresh before retrying; the case may already have been saved.");
      }
    }, 20000);
    setBusy(true);
    try {
      const payload = { ...content, status };
      const record = selected ? await updateFeedbackImprovement(selected.id, payload, selected.version, controller.signal)
        : await createFeedbackImprovement(payload, controller.signal);
      if (!validRecord(record)) throw new Error("Invalid review case");
      if (controller.signal.aborted || mutation.current !== controller) return;
      setSelected(record); setContent(record.content);
      if (status !== "investigating") setPanel("release");
      else if (content.status !== "investigating") setPanel("concern");
      setNotice(status === "released" ? "Release recorded. This does not deploy or retrain a model." : "Improvement case saved.");
      refresh();
    } catch (cause) {
      if (controller.signal.aborted || mutation.current !== controller) return;
      if (cause.status === 401 || cause.status === 403) {
        setDenied(true); setContent(null); setSelected(null); setPage({ items: [], next_cursor: null });
      }
      setError(cause.status === 409 ? cause.message : cause.status === 422
        ? "Check the required fields, review evidence and stage requirements."
        : "The case could not be saved. Refresh before retrying if its status is uncertain.");
    } finally {
      clearTimeout(timer);
      if (mutation.current === controller) { mutation.current = null; setBusy(false); }
    }
  }

  async function remove() {
    if (!selected || !window.confirm("Delete this improvement case and its review notes?")) return;
    const controller = new AbortController(); mutation.current = controller;
    const timer = setTimeout(() => {
      controller.abort();
      if (mutation.current === controller) {
        mutation.current = null; setBusy(false);
        setError("Deletion timed out. Refresh before retrying.");
      }
    }, 20000); setBusy(true);
    try {
      await deleteFeedbackImprovement(selected.id, selected.version, controller.signal);
      if (controller.signal.aborted || mutation.current !== controller) return;
      setSelected(null); setContent(null); setNotice("Improvement case deleted."); refresh();
    } catch (cause) {
      if (controller.signal.aborted || mutation.current !== controller) return;
      if (cause.status === 401 || cause.status === 403) {
        setDenied(true); setContent(null); setSelected(null); setPage({ items: [], next_cursor: null });
      }
      setError(cause.status === 409 ? cause.message : "The case could not be deleted. Refresh before retrying.");
    } finally {
      clearTimeout(timer);
      if (mutation.current === controller) { mutation.current = null; setBusy(false); }
    }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(selected, null, 2) + "\n"], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `improvement-${selected.id}.json`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  const locked = content?.status !== "investigating";
  const messages = <>
    {error && <p ref={editorAlert} role="alert" tabIndex={-1}>{error}</p>}
    {notice && <p role="status">{notice}</p>}
  </>;
  return <section className="admin-improvements" aria-label="Answer improvement workflow">
    <header className="admin-report-toolbar"><h2>Answer improvement cases</h2><div className="improvement-actions">
      <button type="button" disabled={busy || denied} onClick={() => edit()}>New improvement case</button>
      <button type="button" disabled={loading || busy || denied} onClick={() => refresh()}>Refresh cases</button>
    </div></header>
    <p className="admin-report-note">Log recurring or serious concerns. If testing confirms a problem,
      record the fix and its release here. Future answers change after an operator deploys the fix. This workspace does not train or deploy a model.</p>
    {!content && messages}
    {content && <form key={selected?.id || "new"} className="admin-panel improvement-editor" aria-label="Improvement case" onSubmit={event => {
      event.preventDefault(); if (!busy) void save(event.nativeEvent.submitter?.value || "investigating");
    }}>
      <header className="admin-panel-heading">
        <h3 ref={editorHeading} tabIndex={-1}>{selected ? selected.content.title : "New improvement case"}</h3>
        {selected && <span>{stages[content.status]}</span>}
      </header>
      {messages}
      {selected && <div className="improvement-actions improvement-steps" role="group" aria-label="Review steps">
        {Object.entries(panels).filter(([step]) => step !== "release" || locked).map(([step, label]) =>
          <button key={step} type="button" aria-pressed={panel === step} disabled={busy || denied} onClick={event => {
            if (panel === "concern" && step !== "concern" && !event.currentTarget.form.reportValidity()) return;
            setPanel(step); setError("");
          }}>{label}</button>)}
      </div>}
      {panel === "concern" && <fieldset disabled={busy || denied || locked}><legend>Reproduce the concern</legend>
        <div className="improvement-grid">
          <label>Case title<input required minLength="3" maxLength="120" value={content.title} onChange={event => set("title", event.target.value)} /></label>
          <label>Feedback category<select value={content.category} onChange={event => set("category", event.target.value)}>
            {Object.entries(categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select></label>
        </div>
        <label>Scenario<textarea required minLength="3" maxLength="1200" rows="3" aria-describedby="improvement-scenario-help"
          value={content.scenario} onChange={event => set("scenario", event.target.value)} /></label>
        <p className="admin-report-note" id="improvement-scenario-help">Include a test age only if it matters to the concern.</p>
        <label>Expected answer behavior<textarea required minLength="3" maxLength="1200" rows="2" value={content.expected_behavior} onChange={event => set("expected_behavior", event.target.value)} /></label>
        <label className="improvement-check"><input required type="checkbox" checked={content.fictional_confirmed} onChange={event => set("fictional_confirmed", event.target.checked)} />
          I wrote this case without caregiver identifiers or private chat text.</label>
      </fieldset>}
      {panel === "evaluation" && <>
        <fieldset disabled={busy || denied || locked}><legend>Correction and comparison</legend>
          <label>Correction area<select value={content.change_area} onChange={event => set("change_area", event.target.value)}>
            {Object.entries({ prompt: "Coaching instructions", references: "Reference content", retrieval: "Reference retrieval", guardrails: "Safety or scope rules" }).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select></label>
          <label>Correction summary<textarea rows="2" maxLength="1200" value={content.change_summary} onChange={event => set("change_summary", event.target.value)} /></label>
          <label>Change reference<input maxLength="300" placeholder="Commit or pull request reference" value={content.change_reference} onChange={event => set("change_reference", event.target.value)} /></label>
          <p className="admin-report-note">Use the same scenario and test conditions before and after the fix.</p>
          <div className="improvement-grid">{["baseline", "candidate"].map(side => <div className="improvement-capture" key={side}>
            <h4>{side === "baseline" ? "Baseline" : "Candidate"} answer</h4>
            <label>{side === "baseline" ? "Baseline" : "Candidate"} answer text<textarea rows="5" maxLength="6000" value={content[side].answer} onChange={event => setReview(side, "answer", event.target.value)} /></label>
            <details className="improvement-details"><summary>{side === "baseline" ? "Baseline" : "Candidate"} evidence and scores</summary>
            <div className="improvement-capture">
              {Object.entries(captureFields).map(([key, label]) => <label key={key}>{side === "baseline" ? "Baseline" : "Candidate"} {label.toLowerCase()}
                <input maxLength={key === "report_reference" ? 300 : key === "model" ? 120 : 160} value={content[side][key]} onChange={event => setReview(side, key, event.target.value)} /></label>)}
              <label className="improvement-check"><input type="checkbox" checked={content[side].faithfulness_not_applicable} onChange={event => {
                setReview(side, "faithfulness_not_applicable", event.target.checked);
                if (event.target.checked) setReview(side, "scores", { ...content[side].scores, faithfulness: null });
              }} />{side === "baseline" ? "Baseline" : "Candidate"} source support is not applicable (no supplied references).</label>
              {content[side].faithfulness_not_applicable && <label>{side === "baseline" ? "Baseline" : "Candidate"} source-support applicability note
                <input maxLength="500" value={content[side].faithfulness_note} onChange={event => setReview(side, "faithfulness_note", event.target.value)} /></label>}
              {Object.entries(dimensions).map(([key, label]) => <label key={key}>{side === "baseline" ? "Baseline" : "Candidate"} {label.toLowerCase()} score
                <select disabled={key === "faithfulness" && content[side].faithfulness_not_applicable} value={content[side].scores[key] ?? ""} onChange={event => setReview(side, "scores", { ...content[side].scores, [key]: event.target.value ? Number(event.target.value) : null })}>
                  <option value="">Not assessed</option>{[1, 2, 3, 4, 5].map(score => <option key={score} value={score}>{score} / 5</option>)}
                </select></label>)}
            </div>
            </details>
          </div>)}</div>
        </fieldset>
        <fieldset disabled={busy || denied || locked}><legend>Evaluation checks</legend>
          {Object.entries(checkLabels).map(([key, label]) => <label className="improvement-check" key={key}>
            <input type="checkbox" checked={content.checks[key]} onChange={event => set("checks", { ...content.checks, [key]: event.target.checked })} />{label}</label>)}
          <label>Evaluation notes<textarea rows="3" maxLength="2000" value={content.evaluation_notes} onChange={event => set("evaluation_notes", event.target.value)} /></label>
        </fieldset>
      </>}
      {panel === "release" && locked && <fieldset disabled={busy || denied || content.status === "released"}><legend>Deployed fix</legend>
        <p className="admin-report-note">Complete this after the fix is deployed and verified on the live system.</p>
        <label>Deployed commit<input maxLength="40" value={content.release_revision} onChange={event => set("release_revision", event.target.value)} /></label>
        <label>Release notes<textarea rows="2" maxLength="1200" value={content.release_notes} onChange={event => set("release_notes", event.target.value)} /></label>
        <label className="improvement-check"><input type="checkbox" checked={content.deployment_checked} onChange={event => set("deployment_checked", event.target.checked)} />I checked that this correction is deployed.</label>
      </fieldset>}
      <div className="improvement-actions">
        {!locked && <button type="submit" value="investigating" disabled={busy || denied}>
          {panel === "evaluation" ? "Save review draft" : "Save investigation"}</button>}
        {!locked && panel === "evaluation" && <button type="submit" value="ready_for_release" disabled={busy || denied}>Record successful evaluation</button>}
        {panel === "release" && content.status === "ready_for_release" && <button type="submit" value="released" disabled={busy || denied}>Record release</button>}
        <button type="button" disabled={busy} onClick={() => {
          if (canDiscard()) { setContent(null); setSelected(null); }
        }}>Close editor</button>
      </div>
      {selected && <details className="improvement-details"><summary>Case actions</summary>
        <div className="improvement-actions">
          {locked && <button type="button" disabled={busy || denied} onClick={() => void save("investigating")}>Reopen investigation</button>}
          <button type="button" disabled={busy || denied} onClick={download}>Download saved review record</button>
          <button type="button" disabled={busy || denied} onClick={() => void remove()}>Delete case</button>
        </div>
      </details>}
    </form>}
    {loading && <p role="status">Loading improvement cases...</p>}
    {!loading && <div className="admin-panel">
      {page.items.length === 0 ? <p>No improvement cases on this page.</p> : <ul className="improvement-list">{page.items.map(record =>
        <li key={record.id}><button type="button" disabled={busy || denied} onClick={() => edit(record)}>
          <span>{record.content.title}</span><small>{categories[record.content.category]} · {stages[record.content.status]}</small>
        </button></li>)}</ul>}
      <div className="improvement-actions">
        {cursor && <button type="button" disabled={busy || denied} onClick={() => refresh()}>Most recent cases</button>}
        {page.next_cursor && <button type="button" disabled={busy || denied} onClick={() => refresh(page.next_cursor)}>Older cases</button>}
      </div>
    </div>}
  </section>;
}
