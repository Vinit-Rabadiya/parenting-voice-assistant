import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import ChildProfiles from "./ChildProfiles";
import GuidanceAnswer from "./GuidanceAnswer";
import MicrophoneControls from "./MicrophoneControls";
import useConversations from "../hooks/useConversations";
import PrivacyConsent from "./PrivacyConsent";
import ChatLoading from "./ChatLoading";

function ConversationListItem({ conversation, active, disabled, onOpen, onDelete, workspaceActive }) {
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [optionsPosition, setOptionsPosition] = useState({ top: 0, left: 0 });
  const optionsId = useId();
  const rowRef = useRef(null);
  const triggerRef = useRef(null);
  const deleteRef = useRef(null);
  const optionsRef = useRef(null);

  useEffect(() => {
    if (!optionsOpen) return;
    deleteRef.current?.focus();
    function outside(event) {
      if (!rowRef.current?.contains(event.target) && !optionsRef.current?.contains(event.target)) setOptionsOpen(false);
    }
    function escape(event) {
      if (event.key !== "Escape") return;
      setOptionsOpen(false);
      triggerRef.current?.focus();
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("focusin", outside);
    document.addEventListener("keydown", escape);
    function closeOnViewportChange(event) {
      if (!optionsRef.current?.contains(event.target)) setOptionsOpen(false);
    }
    window.addEventListener("scroll", closeOnViewportChange, true);
    window.addEventListener("resize", closeOnViewportChange);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("focusin", outside);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("scroll", closeOnViewportChange, true);
      window.removeEventListener("resize", closeOnViewportChange);
    };
  }, [optionsOpen]);

  return <li ref={rowRef} className="conversation-row">
    <button type="button" disabled={disabled} aria-pressed={active}
      onClick={() => { setOptionsOpen(false); onOpen(conversation.id); }}>{conversation.title}</button>
    <button type="button" className="conversation-more" ref={triggerRef}
      disabled={disabled} aria-label={`More options for ${conversation.title}`}
      aria-expanded={optionsOpen} aria-controls={optionsId}
      onClick={() => {
        const bounds = triggerRef.current.getBoundingClientRect();
        const width = Math.min(200, window.innerWidth - 16);
        setOptionsPosition({ top: Math.max(8, Math.min(bounds.top, window.innerHeight - 64)),
          left: bounds.right + width + 8 <= window.innerWidth ? bounds.right + 6
            : Math.max(8, bounds.right - width), width });
        setOptionsOpen((value) => !value);
      }}><span aria-hidden="true">⋯</span></button>
    {optionsOpen && workspaceActive && createPortal(<div ref={optionsRef} className="conversation-options" id={optionsId} style={optionsPosition}>
      <button type="button" className="delete-action" ref={deleteRef} disabled={disabled}
        onClick={() => { setOptionsOpen(false); triggerRef.current?.focus(); onDelete(conversation.id); }}>Delete conversation</button>
    </div>, document.body)}
  </li>;
}

function ConversationWorkspace({ child, onBusyChange, profileControls, readOnly = false, isActive }) {
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
    if (readOnly || chat.busy || voiceBusy || chat.loading || question.trim().length < 2 || question.length > 1200) return;
    window.speechSynthesis?.cancel();
    const message = question.trim();
    setQuestion("");
    await chat.submit(message, routine, supportCountry);
  }

  if (chat.loading) return <ChatLoading />;
  return <div className={`chat-shell${sidebarOpen ? " chat-shell--history-open" : ""}`}>
    {sidebarOpen && <button type="button" className="history-backdrop" aria-label="Close history" onClick={() => setSidebarOpen(false)} />}
    <aside className="chat-sidebar" aria-label="Conversation history" id="conversation-sidebar">
      <div className="sidebar-brand">Caregiver coaching</div>
      <section className="conversation-history" aria-label="Conversations">
        <button type="button" disabled={readOnly || chat.busy || voiceBusy || chat.loading} onClick={() => {
          chat.newChat(); setQuestion(""); setRoutine(""); setSidebarOpen(false);
        }}>New chat</button>
        <h2 className="history-label">Your conversations</h2>
        {chat.loading && <p role="status">Loading conversations…</p>}
        {chat.historyError && <><p role="alert">History could not be loaded: {chat.historyError}</p>
          <button type="button" disabled={chat.busy || voiceBusy} onClick={chat.loadOlderConversations}>Retry history</button></>}
        {!chat.loading && !chat.historyError && !chat.conversations.length && <p>No saved conversations for this child yet.</p>}
        <ul className="conversation-list">{chat.conversations.map((item) => <ConversationListItem
          key={item.id} conversation={item} active={chat.conversationId === item.id} workspaceActive={isActive}
          disabled={chat.busy || voiceBusy || chat.loading} onDelete={chat.remove}
          onOpen={async (id) => { if (await chat.open(id)) { setQuestion(""); setSidebarOpen(false); } }} />)}</ul>
        {chat.moreConversations && <button type="button" disabled={chat.busy || voiceBusy} onClick={chat.loadOlderConversations}>Load older conversations</button>}
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
          ? <article className="caregiver-message" key={message.id}><h3>You</h3><p>{message.text}</p>
              {message.delivery === "cancelled" && <small role="status">Request cancelled. Stopped waiting for guidance.</small>}
              {message.delivery === "limited" && <small role="status">Request limit reached. No new guidance was generated.</small>}
              {message.delivery === "unconfirmed" && <small>Answer not confirmed. This message is shown locally; reopen the conversation to check saved history.</small>}
            </article>
          : <GuidanceAnswer key={message.id} message={message} childName={child.name} allowFeedback={!readOnly}
              conversationId={message.conversation_id === null ? null : chat.conversationId} />)}
        {!chat.messages.length && <div className="chat-welcome"><h3>What are you doing with your baby today?</h3>
          <p>Describe the moment, or ask for guidance.</p></div>}
        {chat.generating && <p className="guidance-loading" role="status"><span className="guidance-spinner" aria-hidden="true" />Preparing guidance…</p>}
      </section>
      {readOnly ? <p className="chat-composer">Read-only access: you can review or delete existing data. Accept the notice above to request coaching.</p> : <section className="question-panel chat-composer" aria-label="Message composer">
        <form onSubmit={submit}>
          <label className="visually-hidden" htmlFor="caregiver-question">Question</label>
          <textarea ref={composerRef} id="caregiver-question" rows="1" value={question} readOnly={voiceBusy} maxLength={1200}
            onKeyDown={(event) => {
              if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing || event.keyCode === 229) return;
              event.preventDefault();
              if (!event.repeat) event.currentTarget.form?.requestSubmit();
            }}
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
            {isActive && <MicrophoneControls key={chat.conversationId || "new-chat"} compact onTranscriptChange={setQuestion}
              onCaptureStateChange={setVoiceBusy} disabled={chat.busy} />}
            {chat.generating ? <button type="button" className="send-message" aria-label="Stop waiting" title="Stop waiting" onClick={chat.cancelGeneration}>
              <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="1" /></svg>
            </button> : <button type="submit" className="send-message" aria-label="Get guidance" title="Send message" disabled={chat.busy || voiceBusy || chat.loading || question.trim().length < 2 || question.length > 1200}>
              <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5m-6 6 6-6 6 6" /></svg>
            </button>}
          </div>
          <p className="composer-help" aria-live="polite">{voiceBusy
            ? "Voice input in progress. Your words will appear here for review."
            : "Record up to 30 seconds. Review and edit your words here before sending."}</p>
        </form>
        {chat.error && <p role="alert">{chat.error}</p>}
        <details className="conversation-privacy"><summary>Conversation privacy</summary>
          <p>Conversations and feedback stay in your history until you delete the conversation, its child profile, or your account.</p>
          <p>To answer follow-ups, recent messages from this conversation may be sent to the AI service. Reference search may include a recent caregiver message. Recorded audio is processed for transcription and is not deliberately saved by the application.</p>
        </details>
      </section>}
      </div>
    </div>
  </div>;
}

function Workspace({ processingAllowed, isActive }) {
  const [child, setChild] = useState(null);
  const [busy, setBusy] = useState(false);
  const selectChild = useCallback((nextChild) => {
    window.speechSynthesis?.cancel(); setBusy(false); setChild(nextChild);
  }, []);
  const profileControls = <ChildProfiles selectedChild={child} onSelect={selectChild} guidanceBusy={busy} allowChanges={processingAllowed} isActive={isActive} />;
  return <div className="guidance-workspace">
    {child ? <ConversationWorkspace key={child.id} child={child} onBusyChange={setBusy} profileControls={profileControls} readOnly={!processingAllowed} isActive={isActive} />
      : <div className="profile-onboarding">{profileControls}<p>Select or add a child profile first.</p></div>}
  </div>;
}

export default function GuidanceWorkspace({ isActive = true }) {
  return <PrivacyConsent>{(allowed) => <Workspace key={String(allowed)} processingAllowed={allowed} isActive={isActive} />}</PrivacyConsent>;
}
