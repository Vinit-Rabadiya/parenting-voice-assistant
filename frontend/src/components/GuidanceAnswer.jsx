import { useEffect, useId, useRef, useState } from "react";
import { sendFeedback } from "../services/caregiving";

export default function GuidanceAnswer({ message, childName, conversationId, allowFeedback = true }) {
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
  const [audioError, setAudioError] = useState("");
  const utteranceRef = useRef(null);
  const reasonOptions = [
    ["unclear", "Unclear"], ["repeated_advice", "Repeated advice"],
    ["did_not_answer", "Did not answer my message"], ["not_age_appropriate", "Not suited to my child's age"],
  ];

  function clearUtterance() {
    if (utteranceRef.current) {
      utteranceRef.current.onerror = null;
      utteranceRef.current.onend = null;
      utteranceRef.current = null;
    }
  }

  useEffect(() => () => {
    if (!utteranceRef.current) return;
    clearUtterance();
    try { window.speechSynthesis?.cancel(); }
    catch { /* No state updates while removing the answer. */ }
  }, [message.text]);

  function speak(text) {
    setAudioError("");
    if (typeof window.speechSynthesis?.speak !== "function" || typeof window.SpeechSynthesisUtterance !== "function") {
      setAudioError("Audio playback is unavailable in this browser. You can still read the answer.");
      return;
    }
    try {
      clearUtterance();
      window.speechSynthesis.cancel();
      const utterance = new window.SpeechSynthesisUtterance(text);
      utteranceRef.current = utterance;
      utterance.rate = 0.95;
      utterance.onend = () => { if (utteranceRef.current === utterance) utteranceRef.current = null; };
      utterance.onerror = event => {
        if (utteranceRef.current !== utterance) return;
        utteranceRef.current = null;
        if (!["canceled", "interrupted"].includes(event.error)) {
          setAudioError("Audio could not be played. You can still read the answer or try Listen again.");
        }
      };
      window.speechSynthesis.speak(utterance);
    } catch {
      clearUtterance();
      setAudioError("Audio could not be played. You can still read the answer or try Listen again.");
    }
  }

  function stopAudio() {
    clearUtterance();
    setAudioError("");
    try { window.speechSynthesis?.cancel(); }
    catch { setAudioError("Audio controls are unavailable. You can still read the answer."); }
  }

  async function recordFeedback(helpful, numericRating = null) {
    if (!targetId || saving) return;
    setSaving(true);
    try {
      await sendFeedback(targetId, { ...(numericRating === null ? { helpful } : { rating: numericRating }),
        reasons, comment: feedbackComment || null,
        ...(message.interaction_id ? {} : { conversation_id: conversationId }) });
      if (numericRating === null) setRating("");
      setFeedbackStatus("Thanks — your feedback was saved.");
    } catch (cause) { setFeedbackStatus(cause.message); }
    finally { setSaving(false); }
  }

  return (<section className="guidance-answer" aria-live="polite" aria-labelledby={headingId}>
      <h2 id={headingId}>{result.status === "crisis_support" ? "Immediate support"
        : result.status === "caregiver_support" ? "Support for you"
        : result.status === "escalated" ? "Seek urgent medical care"
        : result.status === "safety_blocked" ? "Guidance could not be provided"
        : result.status === "vaccination_notice" ? "Vaccination information"
        : result.response_kind === "clarification" ? "Tell me a little more"
        : result.response_kind === "unrelated" ? "Baby-care topics only"
        : result.response_kind === "professional_referral" ? "Professional advice needed"
        : result.response_kind === "insufficient_references" ? "More information needed"
        : result.status === "no_evidence" ? "No suitable guidance found" : `Guidance for ${childName}`}</h2>
      <p className="guidance-text">{result.answer}</p>
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
        : `Prepared in ${result.processing_seconds.toFixed(2)} seconds using age-aware reference material.`}</p>
      <div className="answer-actions"><button type="button" onClick={() => speak(result.answer)}>Listen</button><button type="button" onClick={stopAudio}>Stop audio</button></div>
      {audioError && <p className="guidance-meta" role="status">{audioError}</p>}
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
      {result.citations.length > 0 && <details className="answer-sources"><summary>Sources used ({result.citations.length})</summary><ul>{result.citations.map((citation) => <li key={citation.passage_id}><a href={citation.source_url} target="_blank" rel="noreferrer">{citation.source_title}{citation.pdf_page != null ? `, page ${citation.pdf_page}` : ""}: {citation.title}</a></li>)}</ul></details>}
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
        <button type="button" disabled={saving || !rating} onClick={() => recordFeedback(null, Number(rating))}>Save rating</button>
        <button type="button" disabled={saving} onClick={() => recordFeedback(true)}>Helpful</button>
        <button type="button" disabled={saving} onClick={() => recordFeedback(false)}>Not helpful</button>
        <p role="status">{feedbackStatus}</p></div>}
    </section>);
}

