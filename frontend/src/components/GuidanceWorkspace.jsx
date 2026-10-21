import { useCallback, useState } from "react";
import MicrophoneControls from "./MicrophoneControls";
import ChildProfiles from "./ChildProfiles";
import { requestCoaching, sendFeedback } from "../services/caregiving";

function speak(text) {
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 0.95;
  window.speechSynthesis.speak(utterance);
}

export default function GuidanceWorkspace() {
  const [child, setChild] = useState(null);
  const [question, setQuestion] = useState("");
  const [routine, setRoutine] = useState("");
  const [supportCountry, setSupportCountry] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [feedbackStatus, setFeedbackStatus] = useState("");
  const [feedbackComment, setFeedbackComment] = useState("");

  const selectChild = useCallback((nextChild) => {
    window.speechSynthesis?.cancel();
    setChild(nextChild);
    setResult(null);
    setFeedbackStatus("");
    setFeedbackComment("");
  }, []);

  async function askForGuidance(event) {
    event.preventDefault();
    if (!child || child.in_scope === false || !question.trim()) return;
    setBusy(true); setError(""); setResult(null); setFeedbackStatus("");
    try {
      setResult(await requestCoaching({ child_id: child.id, question: question.trim(), routine: routine || null,
        support_country: supportCountry || null }));
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  }

  async function recordFeedback(helpful) {
    if (!result?.interaction_id) return;
    try {
      await sendFeedback(result.interaction_id, { helpful, comment: feedbackComment || null });
      setFeedbackStatus("Thanks — your feedback was saved.");
    } catch (cause) { setFeedbackStatus(cause.message); }
  }

  return <div className="guidance-workspace">
    <ChildProfiles selectedChild={child} onSelect={selectChild} guidanceBusy={busy} />
    <section className="question-panel" aria-labelledby="question-title">
      <h2 id="question-title">Ask for guidance</h2>
      <p>{child ? `Guidance will be tailored for ${child.name}, age ${child.age_label}.` : "Select or add a child profile first."}</p>
      {child?.in_scope === false && <p role="status">This profile is outside the coaching age range of birth through the second birthday. You can still manage or delete the profile.</p>}
      <MicrophoneControls onTranscriptChange={setQuestion} />
      <form onSubmit={askForGuidance}>
        <label htmlFor="caregiver-question">Question</label>
        <textarea id="caregiver-question" rows="4" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Type a question, or record one above." />
        <label htmlFor="routine">Routine (optional)</label>
        <select id="routine" value={routine} onChange={(event) => setRoutine(event.target.value)}><option value="">General caregiving</option><option value="feeding">Feeding</option><option value="bathing">Bathing</option><option value="play">Play</option><option value="dressing">Dressing</option><option value="reading">Reading</option></select>
        <label htmlFor="support-country">Support resources location (optional)</label>
        <select id="support-country" value={supportCountry} onChange={(event) => {
          window.speechSynthesis?.cancel(); setResult(null); setSupportCountry(event.target.value);
        }}><option value="">Not selected / other country</option><option value="KE">Kenya</option></select>
        <button type="submit" disabled={busy || !child || child.in_scope === false || question.trim().length < 2}>{busy ? "Preparing guidance…" : "Get guidance"}</button>
      </form>
      {error && <p role="alert">{error}</p>}
    </section>
    {result && <section className="guidance-answer" aria-live="polite" aria-labelledby="guidance-title">
      <h2 id="guidance-title">{result.status === "crisis_support" ? "Immediate support"
        : result.status === "caregiver_support" ? "Support for you"
        : result.status === "escalated" ? "Seek urgent medical care"
        : result.status === "safety_blocked" ? "Guidance could not be provided"
        : result.status === "no_evidence" ? "No suitable guidance found" : `Guidance for ${child?.name}`}</h2>
      <p className="guidance-text">{result.answer}</p>
      <p className="guidance-meta">{["crisis_support", "caregiver_support"].includes(result.status)
        ? "A support message is shown instead of generated developmental coaching."
        : result.status === "escalated"
        ? "Coaching was skipped because your message may describe a danger sign."
        : result.status === "safety_blocked"
        ? "The generated response was withheld by the coaching safety checks."
        : result.status === "no_evidence"
        ? `References checked in ${result.processing_seconds.toFixed(2)} seconds. No coaching answer was generated.`
        : `Prepared in ${result.processing_seconds.toFixed(2)} seconds using age-aware reference material.`}</p>
      <div className="answer-actions"><button type="button" onClick={() => speak(result.answer)}>Listen</button><button type="button" onClick={() => window.speechSynthesis.cancel()}>Stop audio</button></div>
      {result.support_resources?.length > 0 && <section aria-label="Support contacts">
        <h3>Kenya support contacts</h3><p>These contacts apply to Kenya. No call or report is made automatically.</p>
        <ul>{result.support_resources.map((resource) => <li key={resource.service}>
          {resource.service}: <a href={resource.url}>{resource.label}</a>
          <p>{resource.availability}</p>
          <a href={resource.source_url} target="_blank" rel="noreferrer">Service information</a>
          <p>Resource information checked: {resource.verified_on}</p>
        </li>)}</ul>
      </section>}
      {result.citations.length > 0 && <><h3>Sources used</h3><ul>{result.citations.map((citation) => <li key={citation.passage_id}><a href={citation.source_url} target="_blank" rel="noreferrer">{citation.source_title}{citation.pdf_page != null ? `, page ${citation.pdf_page}` : ""}: {citation.title}</a></li>)}</ul></>}
      {result.interaction_id && <div className="feedback"><p>Was this helpful?</p><label htmlFor="feedback-comment">Optional comment<input id="feedback-comment" maxLength="500" value={feedbackComment} onChange={(event) => setFeedbackComment(event.target.value)} /></label><button type="button" onClick={() => recordFeedback(true)}>Helpful</button><button type="button" onClick={() => recordFeedback(false)}>Not helpful</button><p role="status">{feedbackStatus}</p></div>}
    </section>}
  </div>;
}
