import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { createChild, listChildren, updateChild, deleteChild } from "../services/caregiving";
import "./ChildProfiles.css";
import ChatLoading from "./ChatLoading";
import { publishChildProfiles, readChildSelection, saveChildSelection } from "../services/childSelection";

const HEALTH_FIELDS = [
  ["allergies", "Known allergies"], ["conditions", "Diagnosed conditions"],
  ["history", "Relevant health history"], ["care_instructions", "Clinician's care instructions"],
  ["test_result_notes", "Test-result notes"],
];

export default function ChildProfiles({ selectedChild, onSelect, userId, guidanceBusy = false, allowChanges = true, isActive = true, initialChildren, onProfilesChange,
  lazy = false, triggerLabel, persistSelection = true }) {
  const [loadRequested, setLoadRequested] = useState(!lazy);
  const [children, setChildren] = useState([]);
  const [name, setName] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [milestones, setMilestones] = useState([]);
  const [healthDetails, setHealthDetails] = useState({});
  const [useHealthDetails, setUseHealthDetails] = useState(false);
  const [mode, setMode] = useState(null);
  const [pickerPosition, setPickerPosition] = useState(null);
  const [busy, setBusy] = useState(!lazy);
  const [error, setError] = useState("");
  const [initialLoading, setInitialLoading] = useState(true);
  const triggerRef = useRef(null);
  const pickerRef = useRef(null);
  const dialogRef = useRef(null);
  const pickerId = useId();
  const headingId = useId();
  const initialSelection = useRef(selectedChild?.id);
  const initialProfiles = useRef({ userId, children: initialChildren });
  const pickerOpen = pickerPosition !== null;
  const healthContextAvailable = selectedChild?.health_context_available === true;
  const selectChild = useCallback((child) => {
    if (persistSelection) saveChildSelection(userId, child?.id);
    onSelect(child);
  }, [userId, onSelect, persistSelection]);

  useEffect(() => {
    if (!loadRequested) return;
    let active = true;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    const seed = initialProfiles.current.userId === userId ? initialProfiles.current.children : undefined;
    const profiles = Array.isArray(seed) ? Promise.resolve(seed) : listChildren(controller.signal);
    profiles.then((items) => {
      if (!active) return;
      setChildren(items);
      onProfilesChange?.(items);
      const savedId = initialSelection.current || readChildSelection(userId);
      const restored = items.find((item) => item.id === savedId) || items[0] || null;
      selectChild(restored);
      if (lazy) positionPicker();
    }).catch((cause) => {
      if (!active) return;
      setError(controller.signal.aborted ? "Profiles could not be loaded. Please retry." : cause.message);
      if (lazy) setLoadRequested(false);
    })
      .finally(() => { clearTimeout(timer); if (active) { setBusy(false); setInitialLoading(false); } });
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [selectChild, userId, onProfilesChange, loadRequested, lazy]);

  useEffect(() => {
    const updateProfiles = event => {
      if (event.detail?.userId === userId) setChildren(event.detail.children);
    };
    window.addEventListener("child-profiles-updated", updateProfiles);
    return () => window.removeEventListener("child-profiles-updated", updateProfiles);
  }, [userId]);

  useEffect(() => {
    if (!pickerOpen) return;
    pickerRef.current?.querySelector("button")?.focus();
    function outside(event) {
      if (!pickerRef.current?.contains(event.target) && !triggerRef.current?.contains(event.target)) setPickerPosition(null);
    }
    function escape(event) {
      if (event.key !== "Escape") return;
      setPickerPosition(null);
      triggerRef.current?.focus();
    }
    function scroll(event) {
      if (!pickerRef.current?.contains(event.target)) setPickerPosition(null);
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("focusin", outside);
    document.addEventListener("keydown", escape);
    window.addEventListener("scroll", scroll, true);
    window.addEventListener("resize", scroll);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("focusin", outside);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("scroll", scroll, true);
      window.removeEventListener("resize", scroll);
    };
  }, [pickerOpen]);

  useEffect(() => {
    if (!mode || !isActive) return;
    const dialog = dialogRef.current;
    dialog.showModal();
    return () => { if (dialog.open) dialog.close(); };
  }, [mode, isActive]);

  function positionPicker() {
    const bounds = triggerRef.current.getBoundingClientRect();
    const width = Math.min(300, window.innerWidth - 16);
    const availableBelow = window.innerHeight - bounds.bottom - 16;
    const height = Math.min(340, Math.max(120, window.innerHeight - 16));
    const top = availableBelow >= height ? bounds.bottom + 6 : Math.max(8, bounds.top - height - 6);
    setPickerPosition({ top, left: Math.max(8, Math.min(bounds.left, window.innerWidth - width - 8)), width,
      maxHeight: Math.min(height, window.innerHeight - top - 8) });
  }

  function togglePicker() {
    if (lazy && !loadRequested) {
      setBusy(true); setError(""); setLoadRequested(true); return;
    }
    if (pickerOpen) { setPickerPosition(null); return; }
    positionPicker();
  }

  function openDetails(nextMode) {
    if (!allowChanges && nextMode !== "view") return;
    setPickerPosition(null);
    setError("");
    setName(nextMode === "edit" ? selectedChild.name : "");
    setDateOfBirth(nextMode === "edit" ? selectedChild.date_of_birth : "");
    setMilestones(nextMode === "edit" ? selectedChild.milestones || [] : []);
    setHealthDetails(nextMode === "edit" ? selectedChild.health_details || {} : {});
    setUseHealthDetails(nextMode === "edit" && healthContextAvailable && selectedChild.use_health_details === true);
    setMode(nextMode);
  }

  function closeDialog() {
    if (busy) return;
    dialogRef.current?.close();
    setMode(null); setError(""); triggerRef.current?.focus();
  }

  async function saveChild(event) {
    event.preventDefault();
    if (busy || guidanceBusy || !allowChanges) return;
    setBusy(true); setError("");
    try {
      const values = { name, date_of_birth: dateOfBirth,
        milestones: milestones.map((value) => value.trim()).filter(Boolean),
        health_details: Object.fromEntries(HEALTH_FIELDS.map(([key]) => [key, (healthDetails[key] || "").trim()])),
        use_health_details: useHealthDetails };
      const child = mode === "edit" ? await updateChild(selectedChild.id, values) : await createChild(values);
      const nextChildren = mode === "edit" ? children.map((item) => item.id === child.id ? child : item) : [...children, child];
      setChildren(nextChildren); onProfilesChange?.(nextChildren);
      dialogRef.current?.close(); setMode(null); selectChild(child); triggerRef.current?.focus();
      publishChildProfiles(userId, nextChildren);
    } catch (cause) { setError(cause.message); }
    finally { setBusy(false); }
  }

  async function removeChild() {
    if (!selectedChild || busy || guidanceBusy) return;
    if (!window.confirm(`Delete ${selectedChild.name}'s profile and all related conversations and feedback? This cannot be undone.`)) return;
    setBusy(true); setError("");
    try {
      await deleteChild(selectedChild.id);
      const remaining = children.filter((item) => item.id !== selectedChild.id);
      dialogRef.current?.close(); setChildren(remaining); onProfilesChange?.(remaining); setMode(null); selectChild(remaining[0] || null);
      triggerRef.current?.focus();
      publishChildProfiles(userId, remaining);
    } catch (cause) { setError(cause.message); }
    finally { setBusy(false); }
  }

  if (initialLoading && !lazy && !selectedChild) return <ChatLoading />;
  return <div className="child-profile-control">
    <button type="button" className="child-profile-trigger" ref={triggerRef} disabled={busy || guidanceBusy}
      aria-label={triggerLabel} aria-expanded={pickerOpen} aria-controls={pickerId} aria-haspopup="dialog" onClick={togglePicker}>
      <span><strong>{triggerLabel || selectedChild?.name || "Choose child profile"}</strong>
        <small>{selectedChild?.age_label || "Add or select a child"}</small></span>
      <svg className="profile-picker-chevron" aria-hidden="true" width="18" height="18" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m6 9 6 6 6-6" />
      </svg>
    </button>
    {busy && !children.length && !mode && <p role="status">Loading profiles…</p>}
    {error && !mode && <p role="alert">{error}</p>}
    {pickerOpen && isActive && createPortal(<div className="child-profile-popover" ref={pickerRef} id={pickerId}
      role="dialog" aria-label="Choose child profile" style={pickerPosition}>
      <p className="profile-popover-label">Child profiles</p>
      <div className="profile-picker-list">{children.map((child) => <button type="button" key={child.id} disabled={busy || guidanceBusy}
        aria-pressed={child.id === selectedChild?.id} onClick={() => {
          setPickerPosition(null); selectChild(child); triggerRef.current?.focus();
        }}><span>{child.name}<small>{child.age_label}</small></span>
        {child.id === selectedChild?.id && <span aria-hidden="true">✓</span>}</button>)}</div>
      {selectedChild && <><button type="button" disabled={busy || guidanceBusy} onClick={() => openDetails("view")}>View child details</button>
        {allowChanges && <button type="button" disabled={busy || guidanceBusy} onClick={() => openDetails("edit")}>Edit child profile</button>}</>}
      {allowChanges && <button type="button" disabled={busy || guidanceBusy} onClick={() => openDetails("add")}>＋ Add child</button>}
    </div>, document.body)}
    {mode && isActive && createPortal(<dialog ref={dialogRef} className="child-profile-dialog" aria-labelledby={headingId}
      onCancel={(event) => { event.preventDefault(); closeDialog(); }}>
      <header className="profile-dialog-header"><h2 id={headingId}>{mode === "add" ? "Add child" : mode === "edit" ? "Edit child profile" : "Child details"}</h2>
        <button type="button" disabled={busy} aria-label="Close child profile" onClick={closeDialog}>×</button></header>
      {mode === "view" ? <div className="profile-details">
        <dl><dt>Name</dt><dd>{selectedChild.name}</dd><dt>Date of birth</dt><dd>{selectedChild.date_of_birth}</dd>
          <dt>Age</dt><dd>{selectedChild.age_label}</dd></dl>
        <h3>Baseline developmental focus</h3>
        <ul>{(selectedChild.baseline_milestones || []).map((milestone) => <li key={milestone}>{milestone}</li>)}</ul>
        {selectedChild.milestones?.length > 0 && <><h3>Additional milestones</h3>
          <ul>{selectedChild.milestones.map((milestone, index) => <li key={index}>{milestone}</li>)}</ul></>}
        {HEALTH_FIELDS.some(([key]) => selectedChild.health_details?.[key]) && <details className="profile-health-notes">
          <summary>Health and care details</summary>
          <p>{healthContextAvailable && selectedChild.use_health_details ? "Used to tailor replies." : "Saved privately; not used in replies."}</p>
          <dl>{HEALTH_FIELDS.filter(([key]) => selectedChild.health_details?.[key]).map(([key, label]) => <div key={key}>
            <dt>{label}</dt><dd>{selectedChild.health_details[key]}</dd>
          </div>)}</dl>
        </details>}
        <div className="profile-dialog-actions">{allowChanges && <button type="button" disabled={busy || guidanceBusy} onClick={() => openDetails("edit")}>Edit child profile</button>}
          <button type="button" className="delete-action" disabled={busy || guidanceBusy} onClick={removeChild}>Delete child profile</button></div>
      </div> : <form className="child-form" onSubmit={saveChild}>
        <fieldset disabled={busy || guidanceBusy} className="profile-form-fields">
          <label>Child name<input autoFocus required value={name} maxLength="60" onChange={(event) => setName(event.target.value)} /></label>
          <label>Date of birth<input required type="date" value={dateOfBirth} onChange={(event) => setDateOfBirth(event.target.value)} /></label>
          <fieldset className="optional-milestones"><legend>Additional milestones (optional)</legend>
            <p>You can save the profile without adding milestones.</p>
            {milestones.map((milestone, index) => <div className="milestone-entry" key={index}>
              <label htmlFor={`milestone-${index}`}>Milestone {index + 1}<input id={`milestone-${index}`} value={milestone} maxLength={120}
                onChange={(event) => setMilestones((current) => current.map((value, position) => position === index ? event.target.value : value))} /></label>
              <button type="button" aria-label={`Remove milestone ${index + 1}`} onClick={() => setMilestones((current) => current.filter((_, position) => position !== index))}>Remove</button>
            </div>)}
            <button type="button" disabled={milestones.length >= 20} onClick={() => setMilestones((current) => [...current, ""])}>Add milestone</button>
          </fieldset>
          <details className="profile-health-notes">
            <summary>Health and care details (optional)</summary>
            <p>Add short notes relevant to everyday care. These notes are not a medical assessment.</p>
            <div className="profile-health-fields">{HEALTH_FIELDS.map(([key, label]) => <label key={key}>{label}
              <textarea rows={2} maxLength={600} value={healthDetails[key] || ""}
                onChange={(event) => setHealthDetails((current) => ({ ...current, [key]: event.target.value }))} />
            </label>)}</div>
            {mode === "edit" && <label className="profile-health-choice"><input type="checkbox" checked={useHealthDetails}
              disabled={!healthContextAvailable} onChange={(event) => setUseHealthDetails(event.target.checked)} />
              Use health details to tailor replies</label>}
            <p>{mode === "add" ? "Notes are saved privately. After saving, open Edit child profile to manage their use in replies."
              : healthContextAvailable ? "Only enable this if you want these notes included when creating replies." : "These notes can be saved privately. Using them in replies is currently unavailable."}</p>
          </details>
        </fieldset>
        <div className="profile-dialog-actions"><button type="button" disabled={busy} onClick={closeDialog}>Cancel</button>
          <button disabled={busy || guidanceBusy} type="submit">{busy ? "Saving…" : mode === "edit" ? "Save changes" : "Save child"}</button></div>
      </form>}
      {error && <p role="alert">{error}</p>}
    </dialog>, document.body)}
  </div>;
}
