import { useId, useState } from "react";
import { sendFeedback } from "../services/caregiving";

export default function GuidanceAnswer({ message, childName, conversationId, allowFeedback = true }) {
  const headingId = useId();
  const commentId = useId();
  const result = { ...message, answer: message.text,
    processing_seconds: message.processing_seconds ?? 0, citations: message.citations || [] };
  const messageId = message.message_id === null ? null : message.message_id || message.id;
  const targetId = allowFeedback && (message.interaction_id || (conversationId && messageId));
  const [feedbackStatus, setFeedbackStatus] = useState(message.feedback ? "Feedback saved." : "");
  const [feedbackComment, setFeedbackComment] = useState(message.feedback?.comment || "");
  const [saving, setSaving] = useState(false);

  function speak(text) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95;
    window.speechSynthesis.speak(utterance);
  }

  async function recordFeedback(helpful) {
    if (!targetId || saving) return;
    setSaving(true);
    try {
      await sendFeedback(targetId, { helpful, comment: feedbackComment || null,
        ...(message.interaction_id ? {} : { conversation_id: conversationId }) });
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
        ? `References checked in ${result.processing_seconds.toFixed(2)} seconds. No coaching answer was generated.`
        : `Prepared in ${result.processing_seconds.toFixed(2)} seconds using age-aware reference material.`}</p>
      <div className="answer-actions"><button type="button" onClick={() => speak(result.answer)}>Listen</button><button type="button" onClick={() => window.speechSynthesis.cancel()}>Stop audio</button></div>
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
      {targetId && <div className="feedback"><p>Was this helpful?</p><label htmlFor={commentId}>Optional comment<input id={commentId} maxLength="500" value={feedbackComment} onChange={(event) => setFeedbackComment(event.target.value)} /></label><button type="button" onClick={() => recordFeedback(true)}>Helpful</button><button type="button" onClick={() => recordFeedback(false)}>Not helpful</button><p role="status">{feedbackStatus}</p></div>}
    </section>);
}

