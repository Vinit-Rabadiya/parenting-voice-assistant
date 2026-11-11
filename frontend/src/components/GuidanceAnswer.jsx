import { memo, useId, useState } from "react";
import { sendFeedback } from "../services/caregiving";
import useGuidanceAudio from "../hooks/useGuidanceAudio";
import GuidanceText from "./GuidanceText";

function GuidanceAnswer({ message, childName, conversationId, allowFeedback = true, fresh = false, automaticPlayback = true,
  active = true, pending = false }) {
  const headingId = useId();
  const commentId = useId();
  const ratingId = useId();
  // Older saved answers may contain this presentation label. Remove it for
  // both display and playback without changing the stored conversation.
  const answer = message.text.replace(/(^|\n)[ \t]*(?:#{1,6}[ \t]+)?(?:\*\*)?General information(?:\*\*)?[ \t]*:(?:\*\*)?[ \t]*(?:\r?\n)?/gi, "$1");
  const result = { ...message, answer,
    processing_seconds: message.processing_seconds ?? 0, citations: message.citations || [] };
  const contacts = (result.support_resources || []).filter((resource) => resource.category !== "hospital");
  const hospitals = (result.support_resources || []).filter((resource) => resource.category === "hospital");
  const messageId = message.message_id === null ? null : message.message_id || message.id;
  const targetId = allowFeedback && !pending && (message.interaction_id || (conversationId && messageId));
  const [feedbackStatus, setFeedbackStatus] = useState(message.feedback ? "Feedback saved." : "");
  const [feedbackComment, setFeedbackComment] = useState(message.feedback?.comment || "");
  const [saving, setSaving] = useState(false);
  const [rating, setRating] = useState(message.feedback?.rating || "");
  const [reasons, setReasons] = useState(message.feedback?.reasons || []);
  const audio = useGuidanceAudio(result.answer, { automatic: fresh && automaticPlayback && !pending, active: active && !pending });
  const audioBusy = ["preparing", "playing"].includes(audio.state);
  const reasonOptions = [
    ["unclear", "Unclear"], ["repeated_advice", "Repeated advice"],
    ["did_not_answer", "Did not answer my message"], ["not_age_appropriate", "Not suited to my child's age"],
  ];

  async function recordFeedback() {
    if (!targetId || saving || !rating) return;
    setSaving(true);
    try {
      await sendFeedback(targetId, { rating: Number(rating),
        reasons, comment: feedbackComment || null,
        ...(message.interaction_id ? {} : { conversation_id: conversationId }) });
      setFeedbackStatus("Thanks — your feedback was saved.");
    } catch (cause) { setFeedbackStatus(cause.message); }
    finally { setSaving(false); }
  }

  const contactItem = (resource) => <li key={resource.url}>
    {resource.service}{resource.location ? ` — ${resource.location}` : ""}: <a href={resource.url}>{resource.label}</a>
    <p>{resource.availability}</p>
    <a href={resource.source_url} target="_blank" rel="noreferrer">Service information</a>
    <p>Contact checked: {resource.verified_on}</p>
  </li>;

  return (<section className="guidance-answer" data-message-id={message.id} aria-labelledby={headingId}>
      <h2 id={headingId}>{result.status === "crisis_support" ? "Immediate support"
        : result.status === "caregiver_support" ? "Support for you"
        : result.status === "escalated" ? "Seek urgent medical care"
        : result.status === "safety_blocked" ? "Guidance could not be provided"
        : result.status === "vaccination_notice" ? "Vaccination information"
        : result.response_kind === "clarification" ? "Tell me a little more"
        : result.response_kind === "unsupported_language" ? "Please use English"
        : result.response_kind === "age_out_of_scope" ? "Supported age range"
        : result.response_kind === "unrelated" ? "Baby-care topics only"
        : result.response_kind === "professional_referral" ? "Professional advice needed"
        : result.response_kind === "insufficient_references" ? "More information needed"
        : result.status === "no_evidence" ? "No suitable guidance found" : `Guidance for ${childName}`}</h2>
      <GuidanceText text={result.answer} />
      {!pending && <p className="guidance-meta">Response time: {result.processing_seconds.toFixed(2)} seconds.</p>}
      <div className="answer-actions"><button type="button" disabled={!active || pending} aria-label={audioBusy ? "Stop audio" : "Listen"}
        onClick={() => { if (audioBusy) audio.stop(); else audio.play(); }}>
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          {audioBusy ? <rect x="6" y="6" width="12" height="12" rx="1" /> : <path d="M7 4v16l14-8z" />}
        </svg>{audioBusy ? "Stop audio" : "Listen"}</button>
        <span className="guidance-meta" role="status">{audio.state === "preparing" ? "Loading audio…" : audio.message}</span>
        {audio.hint && <div className="audio-help" role="status">
          <span>Can't hear the guidance? Check your device volume.</span>
          <button type="button" aria-label="Dismiss audio help" onClick={audio.dismissHint}>×</button>
        </div>}
      </div>
      {result.status === "vaccination_notice" && result.vaccination_country && <p className="guidance-meta">
        Vaccination country: {result.vaccination_country === "KE" ? "Kenya" : "Another country"}
      </p>}
      {result.support_resources?.length > 0 && <section aria-label="Support contacts">
        <h3>{result.status === "escalated" ? "Kenya emergency contacts" : "Kenya support contacts"}</h3>
        <p>Tap a number to call. No call or report is made automatically.</p>
        <ul>{contacts.map(contactItem)}</ul>
        {hospitals.length > 0 && <details className="hospital-contacts">
          <summary>Hospital contacts in Kenya ({hospitals.length})</summary>
          <p>Use your nearest emergency department. These general hospital contacts are listed by town.</p>
          <ul>{hospitals.map(contactItem)}</ul>
        </details>}
      </section>}
      {result.citations.length > 0 && <details className="answer-sources"><summary>References consulted ({result.citations.length})</summary><ul>{result.citations.map((citation) => <li key={citation.passage_id}><a href={citation.source_url} target="_blank" rel="noreferrer">{citation.source_title}{citation.pdf_page != null ? `, page ${citation.pdf_page}` : ""}: {citation.title}</a></li>)}</ul></details>}
      {targetId && <div className="feedback"><p>Was this helpful?</p>
        <label htmlFor={ratingId}>Helpfulness rating</label>
        <select id={ratingId} value={rating} disabled={saving} onChange={(event) => { setRating(event.target.value); setFeedbackStatus(""); }}>
          <option value="">Choose a rating</option>
          {["Not helpful", "Slightly helpful", "Somewhat helpful", "Helpful", "Very helpful"].map((label, index) =>
            <option key={label} value={index + 1}>{index + 1} — {label}</option>)}
        </select>
        <details className="feedback-details"><summary>Add an optional reason</summary>
        <fieldset disabled={saving}><legend>Optional reasons</legend>
          {reasonOptions.map(([value, label]) => <label key={value}>
            <input type="checkbox" checked={reasons.includes(value)} onChange={(event) => {
              setReasons((items) => event.target.checked ? [...items, value] : items.filter((item) => item !== value));
              setFeedbackStatus("");
            }} />{label}
          </label>)}
        </fieldset>
        </details>
        <label htmlFor={commentId}>Optional comment<input id={commentId} aria-describedby={`${commentId}-notice`} maxLength="500" value={feedbackComment} onChange={(event) => { setFeedbackComment(event.target.value); setFeedbackStatus(""); }} /></label>
        <p id={`${commentId}-notice`} className="guidance-meta">Administrators can read your comment to improve the service. Do not include names or private details.</p>
        <button type="button" disabled={saving || !rating} onClick={recordFeedback}>{saving ? "Saving feedback…" : "Save feedback"}</button>
        <p role="status">{feedbackStatus}</p></div>}
    </section>);
}

// Draft typing and sidebar changes do not change saved answers. Keep each
// answer's parsing, feedback controls and audio hooks out of those renders.
export default memo(GuidanceAnswer);

