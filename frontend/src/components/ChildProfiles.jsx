import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { createChild, listChildren, updateChild, deleteChild } from "../services/caregiving";
import "./ChildProfiles.css";

export default function ChildProfiles({ selectedChild, onSelect, guidanceBusy = false, allowChanges = true }) {
  const [children, setChildren] = useState([]);
  const [name, setName] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [milestones, setMilestones] = useState([]);
  const [mode, setMode] = useState(null);
  const [pickerPosition, setPickerPosition] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const triggerRef = useRef(null);
  const pickerRef = useRef(null);
  const dialogRef = useRef(null);
  const pickerId = useId();
  const headingId = useId();
  const initialSelection = useRef(selectedChild?.id);
  const pickerOpen = pickerPosition !== null;

  useEffect(() => {
    let active = true;
    listChildren().then((items) => {
      if (!active) return;
      setChildren(items);
      if (!initialSelection.current && items[0]) onSelect(items[0]);
    }).catch((cause) => active && setError(cause.message)).finally(() => active && setBusy(false));
    return () => { active = false; };
  }, [onSelect]);

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
    document.addEventListener("keydown", escape);
    window.addEventListener("scroll", scroll, true);
    window.addEventListener("resize", scroll);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("scroll", scroll, true);
      window.removeEventListener("resize", scroll);
    };
  }, [pickerOpen]);

  useEffect(() => {
    if (!mode) return;
    const dialog = dialogRef.current;
    dialog.showModal();
    return () => { if (dialog.open) dialog.close(); };
  }, [mode]);

  function togglePicker() {
    if (pickerOpen) { setPickerPosition(null); return; }
    const bounds = triggerRef.current.getBoundingClientRect();
    const width = Math.min(300, window.innerWidth - 16);
    const availableBelow = window.innerHeight - bounds.bottom - 16;
    const height = Math.min(340, Math.max(120, window.innerHeight - 16));
    const top = availableBelow >= height ? bounds.bottom + 6 : Math.max(8, bounds.top - height - 6);
    setPickerPosition({ top, left: Math.max(8, Math.min(bounds.left, window.innerWidth - width - 8)), width,
      maxHeight: Math.min(height, window.innerHeight - top - 8) });
  }

  function openDetails(nextMode) {
    if (!allowChanges && nextMode !== "view") return;
    setPickerPosition(null);
    setError("");
    setName(nextMode === "edit" ? selectedChild.name : "");
    setDateOfBirth(nextMode === "edit" ? selectedChild.date_of_birth : "");
    setMilestones(nextMode === "edit" ? selectedChild.milestones || [] : []);
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
        milestones: milestones.map((value) => value.trim()).filter(Boolean) };
      const child = mode === "edit" ? await updateChild(selectedChild.id, values) : await createChild(values);
      setChildren((current) => mode === "edit" ? current.map((item) => item.id === child.id ? child : item) : [...current, child]);
      dialogRef.current?.close(); setMode(null); onSelect(child); triggerRef.current?.focus();
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
      dialogRef.current?.close(); setChildren(remaining); setMode(null); onSelect(remaining[0] || null);
      triggerRef.current?.focus();
    } catch (cause) { setError(cause.message); }
    finally { setBusy(false); }
  }

  return <div className="child-profile-control">
    <button type="button" className="child-profile-trigger" ref={triggerRef} disabled={busy || guidanceBusy}
      aria-expanded={pickerOpen} aria-controls={pickerId} aria-haspopup="dialog" onClick={togglePicker}>
      <span><strong>{selectedChild?.name || "Choose child profile"}</strong>
        <small>{selectedChild?.age_label || "Add or select a child"}</small></span>
      <svg className="profile-picker-chevron" aria-hidden="true" width="18" height="18" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m6 9 6 6 6-6" />
      </svg>
    </button>
    {busy && !children.length && !mode && <p role="status">Loading profiles…</p>}
    {error && !mode && <p role="alert">{error}</p>}
    {pickerOpen && createPortal(<div className="child-profile-popover" ref={pickerRef} id={pickerId}
      role="dialog" aria-label="Choose child profile" style={pickerPosition}>
      <p className="profile-popover-label">Child profiles</p>
      <div className="profile-picker-list">{children.map((child) => <button type="button" key={child.id} disabled={busy || guidanceBusy}
        aria-pressed={child.id === selectedChild?.id} onClick={() => {
          setPickerPosition(null); onSelect(child); triggerRef.current?.focus();
        }}><span>{child.name}<small>{child.age_label}</small></span>
        {child.id === selectedChild?.id && <span aria-hidden="true">✓</span>}</button>)}</div>
      {selectedChild && <><button type="button" disabled={busy || guidanceBusy} onClick={() => openDetails("view")}>View child details</button>
        {allowChanges && <button type="button" disabled={busy || guidanceBusy} onClick={() => openDetails("edit")}>Edit child profile</button>}</>}
      {allowChanges && <button type="button" disabled={busy || guidanceBusy} onClick={() => openDetails("add")}>＋ Add child</button>}
    </div>, document.body)}
    {mode && createPortal(<dialog ref={dialogRef} className="child-profile-dialog" aria-labelledby={headingId}
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
        </fieldset>
        <div className="profile-dialog-actions"><button type="button" disabled={busy} onClick={closeDialog}>Cancel</button>
          <button disabled={busy || guidanceBusy} type="submit">{busy ? "Saving…" : mode === "edit" ? "Save changes" : "Save child"}</button></div>
      </form>}
      {error && <p role="alert">{error}</p>}
    </dialog>, document.body)}
  </div>;
}
