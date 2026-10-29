import { useEffect, useId, useRef, useState } from "react";
import contacts from "../../../shared/kenya-contacts.json";
import { stopGuidanceAudio } from "../hooks/useGuidanceAudio";
import "./EmergencyContacts.css";

export default function EmergencyContacts({ onOpenChange }) {
  const [open, setOpen] = useState(false);
  const dialogRef = useRef(null);
  const triggerRef = useRef(null);
  const closeRef = useRef(null);
  const headingId = useId();

  useEffect(() => {
    if (!open) return;
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    const trigger = triggerRef.current;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    closeRef.current?.focus();
    return () => {
      if (dialog.open) dialog.close();
      document.body.style.overflow = previousOverflow;
      onOpenChange?.(false);
      trigger?.focus();
    };
  }, [open, onOpenChange]);

  function close() {
    setOpen(false);
    onOpenChange?.(false);
  }

  function contactList(category) {
    return <ul className="emergency-contact-list">{contacts.filter((contact) => category === "hospital"
      ? contact.category === "hospital" : contact.category !== "hospital").map((contact) => <li key={contact.url}>
      <div><strong>{contact.service}</strong>{contact.location && <span>{contact.location}</span>}
        <p>{contact.availability}</p>
        <a className="emergency-source" href={contact.source_url} target="_blank" rel="noreferrer">Service information</a>
      </div>
      <a className="emergency-call" href={contact.url} aria-label={`Call ${contact.service} on ${contact.label}`}>{contact.label}</a>
    </li>)}</ul>;
  }

  return <>
    <button type="button" ref={triggerRef} className="emergency-button" aria-haspopup="dialog"
      onClick={() => { stopGuidanceAudio(); setOpen(true); onOpenChange?.(true); }}>
      Emergency
    </button>
    {open && <dialog ref={dialogRef} className="emergency-dialog" aria-labelledby={headingId}
      onCancel={(event) => { event.preventDefault(); close(); }} onClose={close}>
      <header className="emergency-dialog-heading"><h2 id={headingId}>Emergency contacts — Kenya</h2>
        <button type="button" ref={closeRef} onClick={close}>Close</button></header>
      <p>Tap a phone number to open your device’s calling app.</p>
      <section aria-label="Emergency and ambulance services"><h3>Emergency and ambulance</h3>
        {contactList("emergency")}</section>
      <section aria-label="Hospital contacts"><h3>Hospitals by town</h3>
        <p>Use your nearest emergency department. These are general hospital contacts.</p>
        {contactList("hospital")}</section>
      <p className="emergency-contact-note">Contact information checked: {contacts[0].verified_on}. Service availability and charges may vary.</p>
    </dialog>}
  </>;
}
