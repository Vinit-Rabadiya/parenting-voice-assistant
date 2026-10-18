import { useEffect, useState } from "react";
import { createChild, listChildren, updateChild } from "../services/caregiving";

export default function ChildProfiles({ selectedChild, onSelect }) {
  const [children, setChildren] = useState([]);
  const [name, setName] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [milestones, setMilestones] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    listChildren().then((items) => {
      if (!active) return;
      setChildren(items);
      if (!selectedChild && items[0]) onSelect(items[0]);
    }).catch((cause) => active && setError(cause.message)).finally(() => active && setBusy(false));
    return () => { active = false; };
  }, [onSelect, selectedChild]);

  async function addChild(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const values = { name, date_of_birth: dateOfBirth, milestones: milestones.map((value) => value.trim()).filter(Boolean) };
      const child = editingId ? await updateChild(editingId, values) : await createChild(values);
      setChildren((current) => editingId ? current.map((item) => item.id === child.id ? child : item) : [...current, child]);
      onSelect(child);
      setName(""); setDateOfBirth(""); setMilestones([]); setEditingId(null); setShowForm(false);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="child-profiles" aria-labelledby="child-profile-title">
    <div className="section-heading"><h2 id="child-profile-title">Child profile</h2><div className="profile-actions"><button type="button" onClick={() => { setEditingId(null); setName(""); setDateOfBirth(""); setMilestones([]); setShowForm((value) => !value); }}>Add child</button>{selectedChild && <button type="button" onClick={() => { setEditingId(selectedChild.id); setName(selectedChild.name); setDateOfBirth(selectedChild.date_of_birth); setMilestones(selectedChild.milestones || []); setShowForm(true); }}>Edit active child</button>}</div></div>
    {busy && !children.length ? <p role="status">Loading profiles…</p> : children.length ? <><label>Active child<select value={selectedChild?.id || ""} onChange={(event) => onSelect(children.find((child) => child.id === event.target.value))}>{children.map((child) => <option value={child.id} key={child.id}>{child.name} — {child.age_label}</option>)}</select></label>{selectedChild && <div className="milestone-summary"><p>Baseline developmental focus</p><ul>{selectedChild.baseline_milestones.map((milestone) => <li key={milestone}>{milestone}</li>)}</ul></div>}</> : <p>Add a child profile to receive age-aware guidance.</p>}
    {selectedChild?.milestones?.length > 0 && <div className="milestone-summary"><p>Additional milestones</p><ul>{selectedChild.milestones.map((milestone, index) => <li key={index}>{milestone}</li>)}</ul></div>}
    {showForm && <form className="child-form" onSubmit={addChild}>
      <label>Child name<input required value={name} maxLength="60" onChange={(event) => setName(event.target.value)} /></label>
      <label>Date of birth<input required type="date" value={dateOfBirth} onChange={(event) => setDateOfBirth(event.target.value)} /></label>
      <fieldset className="optional-milestones">
        <legend>Additional milestones (optional)</legend>
        <p>You can save the profile without adding milestones.</p>
        {milestones.map((milestone, index) => <div className="milestone-entry" key={index}>
          <label htmlFor={`milestone-${index}`}>Milestone {index + 1}<input id={`milestone-${index}`} value={milestone} maxLength={120} onChange={(event) => setMilestones((current) => current.map((value, position) => position === index ? event.target.value : value))} /></label>
          <button type="button" aria-label={`Remove milestone ${index + 1}`} onClick={() => setMilestones((current) => current.filter((_, position) => position !== index))}>Remove</button>
        </div>)}
        <button type="button" disabled={milestones.length >= 20 || busy} onClick={() => setMilestones((current) => [...current, ""])}>Add milestone</button>
      </fieldset>
      <button disabled={busy} type="submit">{editingId ? "Save changes" : "Save child"}</button>
    </form>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
