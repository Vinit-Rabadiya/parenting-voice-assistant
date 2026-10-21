import { useCallback, useEffect, useRef, useState } from "react";
import ChildProfiles from "./ChildProfiles";
import GuidanceAnswer from "./GuidanceAnswer";
import MicrophoneControls from "./MicrophoneControls";
import useConversations from "../hooks/useConversations";

function ConversationWorkspace({ child, onBusyChange, profileControls }) {
  const chat = useConversations(child.id, onBusyChange);
  const [question, setQuestion] = useState("");
  const [routine, setRoutine] = useState("");
  const [supportCountry, setSupportCountry] = useState("");
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const threadRef = useRef(null);
  const composerRef = useRef(null);
  const lastMessageId = chat.messages.at(-1)?.id;
  useEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [chat.conversationId, lastMessageId]);
  useEffect(() => {
    const input = composerRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
  }, [question]);

  async function submit(event) {
    event.preventDefault();
    if (voiceBusy || chat.loading || child.in_scope === false || question.trim().length < 2 || question.length > 1200) return;
    window.speechSynthesis?.cancel();
    const draft = question;
    if (await chat.submit(question.trim(), routine, supportCountry)) {
      setQuestion((current) => current === draft ? "" : current);
    }
  }

  return <div className={`chat-shell${sidebarOpen ? " chat-shell--history-open" : ""}`}>
    {sidebarOpen && <button type="button" className="history-backdrop" aria-label="Close history" onClick={() => setSidebarOpen(false)} />}
    <aside className="chat-sidebar" aria-label="Conversation history" id="conversation-sidebar">
      <div className="sidebar-brand">Caregiver coaching</div>
      <section className="conversation-history" aria-label="Conversations">
        <button type="button" disabled={chat.busy || voiceBusy || chat.loading} onClick={() => {
          chat.newChat(); setQuestion(""); setRoutine(""); setSidebarOpen(false);
        }}>New chat</button>
        <h2 className="history-label">Your conversations</h2>
        {chat.loading && <p role="status">Loading conversations…</p>}
        {chat.historyError && <><p role="alert">History could not be loaded: {chat.historyError}</p>
          <button type="button" disabled={chat.busy || voiceBusy} onClick={chat.loadOlderConversations}>Retry history</button></>}
        {!chat.loading && !chat.historyError && !chat.conversations.length && <p>No saved conversations for this child yet.</p>}
        <ul className="conversation-list">{chat.conversations.map((item) => <li key={item.id}>
          <button type="button" disabled={chat.busy || voiceBusy || chat.loading} aria-pressed={chat.conversationId === item.id}
            onClick={async () => { if (await chat.open(item.id)) { setQuestion(""); setSidebarOpen(false); } }}>{item.title}</button>
        </li>)}</ul>
        {chat.moreConversations && <button type="button" disabled={chat.busy || voiceBusy} onClick={chat.loadOlderConversations}>Load older conversations</button>}
        {chat.conversationId && <button type="button" className="delete-action" disabled={chat.busy || voiceBusy} onClick={chat.remove}>Delete conversation</button>}
      </section>
      <div className="sidebar-profile">{profileControls}</div>
    </aside>
    <div className={`chat-main${chat.messages.length ? "" : " chat-main--empty"}`}>
      <header className="chat-heading">
        <button type="button" className="history-toggle" aria-controls="conversation-sidebar" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen((value) => !value)}>History</button>
        <h2 id="thread-title">{child.name}</h2><p>{child.age_label}</p>
      </header>
      <div className="chat-stage">
      <section className="conversation-thread" aria-labelledby="thread-title" ref={threadRef} tabIndex={0}>
        {chat.moreMessages && <button type="button" disabled={chat.busy} onClick={chat.loadOlderMessages}>Load earlier messages</button>}
        {chat.messages.map((message) => message.role === "user"
          ? <article className="caregiver-message" key={message.id}><h3>You</h3><p>{message.text}</p></article>
          : <GuidanceAnswer key={message.id} message={message} childName={child.name}
              conversationId={message.conversation_id === null ? null : chat.conversationId} />)}
        {!chat.messages.length && <div className="chat-welcome"><h3>What are you doing with your baby today?</h3>
          <p>Describe the moment, or ask for guidance.</p></div>}
        {chat.busy && <p role="status">Preparing guidance…</p>}
      </section>
      <section className="question-panel chat-composer" aria-label="Message composer">
        {child.in_scope === false && <p role="status">This profile is outside the coaching age range. Saved conversations remain available.</p>}
        <form onSubmit={submit}>
          <label className="visually-hidden" htmlFor="caregiver-question">Question</label>
          <textarea ref={composerRef} id="caregiver-question" rows="1" value={question} readOnly={voiceBusy} maxLength={1200}
            onChange={(event) => setQuestion(event.target.value)} placeholder="Type a message, or use the microphone…" />
          <details className="composer-options"><summary aria-label="Routine and support location">＋</summary>
            <div className="composer-option-fields">
              <label htmlFor="routine">Routine (optional)</label>
              <select id="routine" value={routine} onChange={(event) => setRoutine(event.target.value)}>
                <option value="">General caregiving</option><option value="feeding">Feeding</option><option value="bathing">Bathing</option>
                <option value="play">Play</option><option value="dressing">Dressing</option><option value="reading">Reading</option>
              </select>
              <label htmlFor="support-country">Support resources location (optional)</label>
              <select id="support-country" value={supportCountry} onChange={(event) => {
                window.speechSynthesis?.cancel(); setSupportCountry(event.target.value);
              }}><option value="">Not selected / other country</option><option value="KE">Kenya</option></select>
            </div>
          </details>
          <div className="composer-actions">
            <MicrophoneControls key={chat.conversationId || "new-chat"} compact onTranscriptChange={setQuestion}
              onCaptureStateChange={setVoiceBusy} disabled={chat.busy} />
            <button type="submit" className="send-message" aria-label="Get guidance" title="Send message" disabled={chat.busy || voiceBusy || chat.loading || child.in_scope === false || question.trim().length < 2 || question.length > 1200}>
              <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5m-6 6 6-6 6 6" /></svg>
            </button>
          </div>
          <p className="composer-help" aria-live="polite">{voiceBusy
            ? "Voice input in progress. Your words will appear here for review."
            : "Record up to 30 seconds. Review and edit your words here before sending."}</p>
        </form>
        {chat.error && <p role="alert">{chat.error}</p>}
      </section>
      </div>
    </div>
  </div>;
}

export default function GuidanceWorkspace() {
  const [child, setChild] = useState(null);
  const [busy, setBusy] = useState(false);
  const selectChild = useCallback((nextChild) => {
    window.speechSynthesis?.cancel(); setBusy(false); setChild(nextChild);
  }, []);
  const profileControls = <details className="profile-settings" open={!child}>
      <summary>{child ? `Child profile: ${child.name}` : "Choose or add a child profile"}</summary>
      <ChildProfiles selectedChild={child} onSelect={selectChild} guidanceBusy={busy} />
    </details>;
  return <div className="guidance-workspace">
    {child ? <ConversationWorkspace key={child.id} child={child} onBusyChange={setBusy} profileControls={profileControls} />
      : <div className="profile-onboarding">{profileControls}<p>Select or add a child profile first.</p></div>}
  </div>;
}
