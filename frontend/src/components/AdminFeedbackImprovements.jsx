import { useEffect, useImperativeHandle, useRef, useState } from "react";
import {
  createFeedbackImprovement, deleteFeedbackImprovement, listFeedbackImprovements, updateFeedbackImprovement,
} from "../services/caregiving";
import "./AdminFeedbackImprovements.css";

const categories = { unclear: "Unclear", repeated_advice: "Repeated advice", did_not_answer: "Did not answer",
  not_age_appropriate: "Not age appropriate", other: "Other concern" };
const stages = { investigating: "Investigating", ready_for_release: "Evaluation recorded", released: "Release recorded" };
const panels = { concern: "Concern", release: "Release record" };
const newContent = (category = "unclear") => ({ title: "", category, scenario: "", expected_behavior: "",
  fictional_confirmed: false, status: "investigating", release_revision: "", deployment_checked: false, release_notes: "" });

function validRecord(record) {
  const content = record?.content;
  return /^[0-9a-f]{32}$/.test(record?.id) && Number.isSafeInteger(record.version) && record.version > 0
    && content && Object.hasOwn(stages, content.status) && Object.hasOwn(categories, content.category)
    && ["title", "scenario", "expected_behavior", "release_revision", "release_notes"].every(key => typeof content[key] === "string")
    && typeof content.fictional_confirmed === "boolean" && typeof content.deployment_checked === "boolean";
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

  async function save(status) {
    setError(""); setNotice("");
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
      const payload = { ...content, status,
        release_without_evaluation: status === "released" && content.status === "investigating" };
      const record = selected ? await updateFeedbackImprovement(selected.id, payload, selected.version, controller.signal)
        : await createFeedbackImprovement(payload, controller.signal);
      if (!validRecord(record)) throw new Error("Invalid review case");
      if (controller.signal.aborted || mutation.current !== controller) return;
      setSelected(record); setContent(record.content);
      if (status !== "investigating") setPanel("release");
      else if (content.status !== "investigating") setPanel("concern");
      setNotice(status === "released" ? "Release recorded." : "Improvement case saved.");
      refresh();
    } catch (cause) {
      if (controller.signal.aborted || mutation.current !== controller) return;
      if (cause.status === 401 || cause.status === 403) {
        setDenied(true); setContent(null); setSelected(null); setPage({ items: [], next_cursor: null });
      }
      setError(cause.status === 409 ? cause.message : cause.status === 422
        ? "Check the required fields before saving."
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
    <p className="admin-report-note">Save the concern, then record the release once the correction is verified on the live app.</p>
    {!content && messages}
    {content && <form key={selected?.id || "new"} className="admin-panel improvement-editor" aria-label="Improvement case" onSubmit={event => {
      event.preventDefault();
      if (busy || denied) return;
      if (panel === "release" && selected && content.status !== "released") void save("released");
      if (panel === "concern" && !locked) void save("investigating");
    }}>
      <header className="admin-panel-heading">
        <h3 ref={editorHeading} tabIndex={-1}>{selected ? selected.content.title : "New improvement case"}</h3>
        {selected && <span>{stages[content.status]}</span>}
      </header>
      {messages}
      {selected && <div className="improvement-actions improvement-steps" role="group" aria-label="Case sections">
        {Object.entries(panels).map(([step, label]) =>
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
        <p className="admin-report-note" id="improvement-scenario-help">Include an age if it matters to the concern.</p>
        <label>Expected answer behavior<textarea required minLength="3" maxLength="1200" rows="2" value={content.expected_behavior} onChange={event => set("expected_behavior", event.target.value)} /></label>
        <label className="improvement-check"><input required type="checkbox" checked={content.fictional_confirmed} onChange={event => set("fictional_confirmed", event.target.checked)} />
          I wrote this case without caregiver identifiers or private chat text.</label>
      </fieldset>}
      {selected && panel === "release" && <fieldset disabled={busy || denied || content.status === "released"}><legend>Deployed fix</legend>
        <p className="admin-report-note">Complete this after the fix is deployed and verified on the live system.</p>
        <label>Deployed commit<input maxLength="40" value={content.release_revision} onChange={event => set("release_revision", event.target.value)} /></label>
        <label>Release notes<textarea rows="2" maxLength="1200" value={content.release_notes} onChange={event => set("release_notes", event.target.value)} /></label>
        <label className="improvement-check"><input type="checkbox" checked={content.deployment_checked} onChange={event => set("deployment_checked", event.target.checked)} />I checked that this correction is deployed.</label>
      </fieldset>}
      <div className="improvement-actions">
        {panel === "concern" && !locked && <button type="submit" disabled={busy || denied}>Save investigation</button>}
        {selected && panel === "release" && content.status !== "released"
          && <button type="submit" disabled={busy || denied}>Record release</button>}
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
