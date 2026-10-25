import { useCallback, useId, useState } from "react";
import { sendFeedback } from "../services/caregiving";
import useGuidanceAudio from "../hooks/useGuidanceAudio";
import GuidanceText from "./GuidanceText";

export default function GuidanceAnswer({ message, childName, conversationId, allowFeedback = true, fresh = false, active = true }) {
  const headingId = useId();
  const commentId = useId();
  const ratingId = useId();
  const result = { ...message, answer: message.text,
    processing_seconds: message.processing_seconds ?? 0, citations: message.citations || [] };
  const messageId = message.message_id === null ? null : message.message_id || message.id;
  const targetId = allowFeedback && (message.interaction_id || (conversationId && messageId));
  const [feedbackStatus, setFeedbackStatus] = useState(message.feedback ? "Feedback saved." : "");
  const [feedbackComment, setFeedbackComment] = useState(message.feedback?.comment || "");
  const [saving, setSaving] = useState(false);
  const [rating, setRating] = useState(message.feedback?.rating || "");
  const [reasons, setReasons] = useState(message.feedback?.reasons || []);
  const animate = fresh && message.status === "answered";
  const [textReady, setTextReady] = useState(!animate);
  const finishText = useCallback(() => setTextReady(true), []);
  const audio = useGuidanceAudio(result.answer, { automatic: fresh, ready: textReady, active });
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

  return (<section className="guidance-answer" data-message-id={message.id} aria-labelledby={headingId}>
      <h2 id={headingId}>{result.status === "crisis_support" ? "Immediate support"
        : result.status === "caregiver_support" ? "Support for you"
        : result.status === "escalated" ? "Seek urgent medical care"
        : result.status === "safety_blocked" ? "Guidance could not be provided"
        : result.status === "vaccination_notice" ? "Vaccination information"
        : result.response_kind === "clarification" ? "Tell me a little more"
        : result.response_kind === "age_out_of_scope" ? "Supported age range"
        : result.response_kind === "unrelated" ? "Baby-care topics only"
        : result.response_kind === "professional_referral" ? "Professional advice needed"
        : result.response_kind === "insufficient_references" ? "More information needed"
        : result.status === "no_evidence" ? "No suitable guidance found" : `Guidance for ${childName}`}</h2>
      <GuidanceText text={result.answer} animate={animate && !textReady} active={active} onComplete={finishText} />
      <p className="guidance-meta">{["crisis_support", "caregiver_support"].includes(result.status)
        ? "A support message is shown instead of generated developmental coaching."
        : result.status === "escalated"
        ? "Coaching was skipped because your message may describe a danger sign."
        : result.status === "safety_blocked"
        ? "The generated response was withheld by the coaching safety checks."
        : result.status === "vaccination_notice"
        ? "No AI-generated vaccination advice was provided."
        : result.status === "no_evidence"
        ? `Processed in ${result.processing_seconds.toFixed(2)} seconds. No coaching answer was generated.`
        : result.answer_basis === "general_information"
        ? `Prepared in ${result.processing_seconds.toFixed(2)} seconds. General information; not verified against reference documents.`
        : `Prepared in ${result.processing_seconds.toFixed(2)} seconds with reference support. Any supplemental information is labelled in the answer.`}</p>
      {result.reference_status === "unavailable" && <p className="guidance-meta">Reference search is temporarily unavailable. This answer uses general information.</p>}
      <div className="answer-actions"><button type="button" disabled={!active} aria-label={audioBusy ? "Stop audio" : "Listen"}
        onClick={() => { if (audioBusy) audio.stop(); else { finishText(); audio.play(); } }}>
        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          {audioBusy ? <rect x="6" y="6" width="12" height="12" rx="1" /> : <path d="M7 4v16l14-8z" />}
        </svg>{audioBusy ? "Stop audio" : "Listen"}</button>
        <span className="guidance-meta" role="status">{!textReady && active ? "Showing guidance…" : audio.state === "preparing" ? "Preparing audio…" : audio.message}</span>
        {audio.hint && <div className="audio-help" role="status">
          <span>Can't hear the guidance? Check your device volume.</span>
          <button type="button" aria-label="Dismiss audio help" onClick={audio.dismissHint}>×</button>
        </div>}
      </div>
      {result.status === "vaccination_notice" && result.vaccination_country && <p className="guidance-meta">
        Vaccination country: {result.vaccination_country === "KE" ? "Kenya" : "Another country"}
      </p>}
      {result.support_resources?.length > 0 && <section aria-label="Support contacts">
        <h3>Kenya support contacts</h3><p>These contacts apply to Kenya. No call or report is made automatically.</p>
        <ul>{result.support_resources.map((resource) => <li key={resource.service}>
          {resource.service}: <a href={resource.url}>{resource.label}</a>
          <p>{resource.availability}</p>
          <a href={resource.source_url} target="_blank" rel="noreferrer">Service information</a>
          <p>Resource information checked: {resource.verified_on}</p>
        </li>)}</ul>
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
        <label htmlFor={commentId}>Optional comment<input id={commentId} maxLength="500" value={feedbackComment} onChange={(event) => { setFeedbackComment(event.target.value); setFeedbackStatus(""); }} /></label>
        <button type="button" disabled={saving || !rating} onClick={recordFeedback}>{saving ? "Saving feedback…" : "Save feedback"}</button>
        <p role="status">{feedbackStatus}</p></div>}
    </section>);
}

