import { useEffect, useRef, useState } from "react";
import { acceptPrivacyConsent, getPrivacyConsent } from "../services/caregiving";
import "./PrivacyConsent.css";
import ChatLoading from "./ChatLoading";

function validNotice(value) {
  return typeof value?.version === "string" && value.version.length > 0
    && typeof value.accepted === "boolean" && Array.isArray(value.notice)
    && value.notice.length > 0 && value.notice.every((item) => typeof item === "string");
}

export default function PrivacyConsent({ children, initialNotice }) {
  // Bootstrap data belongs only to this mounted account workspace. Reloads and
  // server consent challenges always fetch a fresh notice.
  const [initial] = useState(() => validNotice(initialNotice) ? initialNotice : null);
  const [notice, setNotice] = useState(initial);
  const [accepted, setAccepted] = useState(false);
  const [authority, setAuthority] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [readOnly, setReadOnly] = useState(false);
  const saveRequest = useRef(null);

  useEffect(() => () => saveRequest.current?.abort(), []);

  useEffect(() => {
    const reloadRequiredConsent = () => {
      saveRequest.current?.abort();
      setBusy(false); setNotice(null); setAccepted(false); setAuthority(false); setError("");
      setAttempt((value) => value + 1);
    };
    window.addEventListener("privacy-consent-required", reloadRequiredConsent);
    return () => window.removeEventListener("privacy-consent-required", reloadRequiredConsent);
  }, []);

  useEffect(() => {
    if (attempt === 0 && initial) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      controller.abort();
      setError("Unable to load your privacy settings. Please retry.");
    }, 8000);
    getPrivacyConsent(controller.signal).then((value) => {
      if (controller.signal.aborted) return;
      if (!validNotice(value)) throw new Error("The privacy notice could not be read. Please retry.");
      setNotice(value);
    }).catch((cause) => { if (!controller.signal.aborted) setError(cause.message); })
      .finally(() => clearTimeout(timer));
    return () => { clearTimeout(timer); controller.abort(); };
  }, [attempt, initial]);

  async function accept(event) {
    event.preventDefault();
    if (!accepted || !authority || !notice || busy) return;
    const controller = new AbortController();
    saveRequest.current = controller;
    setBusy(true); setError("");
    try {
      const value = await acceptPrivacyConsent(notice.version, controller.signal);
      if (controller.signal.aborted) return;
      if (!validNotice(value) || !value.accepted || value.version !== notice.version) {
        throw new Error("Consent was not confirmed. Reload the notice and try again.");
      }
      setNotice(value);
    } catch (cause) { if (!controller.signal.aborted) setError(cause.message); }
    finally { if (!controller.signal.aborted) setBusy(false); saveRequest.current = null; }
  }

  if (notice?.accepted) return children(true, attempt === 0 && initial?.accepted === true);
  if (!notice && !error) return <ChatLoading />;
  return <div className={`privacy-boundary${readOnly ? " privacy-boundary--history" : ""}`}>
    <section className="privacy-notice" aria-labelledby="privacy-title">
      <h2 id="privacy-title">Privacy and consent</h2>
      {!notice && !error && <p role="status">Loading privacy notice…</p>}
      {notice && <><p>Please read how we use your information before you continue.</p>
        <h3>How your information is used and shared</h3>
        <ul>{notice.notice.map((item) => <li key={item}>{item}</li>)}</ul>
        <p>Notice version: {notice.version}</p>
        <form onSubmit={accept}>
          <label className="consent-choice"><input type="checkbox" checked={authority} disabled={busy}
            onChange={(event) => setAuthority(event.target.checked)} />I am the parent or guardian, or am authorised to provide this child's information.</label>
          <label className="consent-choice"><input type="checkbox" checked={accepted} disabled={busy}
            onChange={(event) => setAccepted(event.target.checked)} />I agree to my information and my child's information being used as explained above.</label>
          <button type="submit" disabled={busy || !accepted || !authority}>{busy ? "Saving consent…" : "Accept and continue"}</button>
        </form></>}
      {error && <p role="alert">{error}</p>}
      <button type="button" disabled={busy} onClick={() => {
        setNotice(null); setAccepted(false); setAuthority(false); setError("");
        setAttempt((value) => value + 1);
      }}>Reload notice</button>
      <button type="button" disabled={busy} onClick={() => setReadOnly((value) => !value)}>
        {readOnly ? "Hide existing data" : "View or delete existing data without accepting"}</button>
      <p>You can also open My Account to delete your account without accepting.</p>
    </section>
    {readOnly && children(false)}
  </div>;
}
