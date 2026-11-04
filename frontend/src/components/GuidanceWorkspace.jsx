import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import ChildProfiles from "./ChildProfiles";
import GuidanceAnswer from "./GuidanceAnswer";
import MicrophoneControls from "./MicrophoneControls";
import useConversations from "../hooks/useConversations";
import PrivacyConsent from "./PrivacyConsent";
import { stopGuidanceAudio } from "../hooks/useGuidanceAudio";
import usePlaybackPreference from "../hooks/usePlaybackPreference";
import { getConversation } from "../services/caregiving";
import { readConversationLocation, setConversationLocation } from "../services/conversationLocation";

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

function ConversationWorkspace({ child, userId, onBusyChange, profileControls, readOnly = false, isActive, visible = true,
  onNavigate, register, initialConversation }) {
  const inputId = useId();
  const routineId = useId();
  const sidebarId = useId();
  const threadTitleId = useId();
  const chat = useConversations(child.id, onBusyChange, onNavigate, initialConversation);
  useEffect(() => {
    register(child.id, { conversationId: chat.conversationId, restore: chat.restore,
      newChat: chat.newChat, cancel: chat.cancelNavigation });
    return () => register(child.id, null);
  }, [child.id, chat.conversationId, chat.restore, chat.newChat, chat.cancelNavigation, register]);
  const { automatic } = usePlaybackPreference(userId);
  const [question, setQuestion] = useState("");
  const [routine, setRoutine] = useState("");
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const threadRef = useRef(null);
  const lastScrollTarget = useRef(null);
  const composerRef = useRef(null);
  const lastMessageId = chat.messages.at(-1)?.id;
  useEffect(() => {
    const thread = threadRef.current;
    if (!thread || !isActive) return;
    const target = Array.from(thread.children).find((item) => item.dataset.messageId === lastMessageId);
    if (!target || target === lastScrollTarget.current) return;
    lastScrollTarget.current = target;
    // Move only the chat scroller to this message, never the whole page's end.
    const top = Math.max(0, thread.scrollTop + target.getBoundingClientRect().top
      - thread.getBoundingClientRect().top - thread.clientTop - 12);
    const behavior = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth";
    if (thread.scrollTo) thread.scrollTo({ top, behavior });
    else thread.scrollTop = top;
  }, [chat.conversationId, lastMessageId, isActive]);
  useEffect(() => {
    const input = composerRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
  }, [question]);

  async function submit(event) {
    event.preventDefault();
    if (readOnly || chat.busy || voiceBusy || question.trim().length < 2 || question.length > 1200) return;
    stopGuidanceAudio();
    const message = question.trim();
    setQuestion("");
    await chat.submit(message, routine, "KE");
  }

  return <div className={`chat-shell${sidebarOpen ? " chat-shell--history-open" : ""}`} hidden={!visible}>
    {sidebarOpen && <button type="button" className="history-backdrop" aria-label="Close history" onClick={() => setSidebarOpen(false)} />}
    <aside className="chat-sidebar" aria-label="Conversation history" id={sidebarId}>
      <div className="sidebar-brand">Caregiver coaching</div>
      <section className="conversation-history" aria-label="Conversations">
        <button type="button" disabled={readOnly || chat.busy || voiceBusy} onClick={() => {
          chat.newChat(); setQuestion(""); setRoutine(""); setSidebarOpen(false);
        }}>New chat</button>
        <h2 className="history-label">Your conversations</h2>
        {chat.loading && <p role="status">Loading conversations…</p>}
        {chat.historyError && <><p role="alert">History could not be loaded: {chat.historyError}</p>
          <button type="button" disabled={chat.busy || voiceBusy} onClick={chat.loadOlderConversations}>Retry history</button></>}
        {!chat.loading && !chat.historyError && !chat.conversations.length && <p>No saved conversations for this child yet.</p>}
        <ul className="conversation-list">{chat.conversations.map((item) => <ConversationListItem
          key={item.id} conversation={item} active={chat.conversationId === item.id} workspaceActive={isActive}
          disabled={chat.busy || voiceBusy} onDelete={chat.remove}
          onOpen={async (id) => { if (await chat.open(id)) { setQuestion(""); setSidebarOpen(false); } }} />)}</ul>
        {chat.moreConversations && <button type="button" disabled={chat.busy || voiceBusy} onClick={chat.loadOlderConversations}>Load older conversations</button>}
      </section>
      <div className="sidebar-profile">{profileControls}</div>
    </aside>
    <div className={`chat-main${chat.messages.length ? "" : " chat-main--empty"}`}>
      <header className="chat-heading">
        <button type="button" className="history-toggle" aria-controls={sidebarId} aria-expanded={sidebarOpen} onClick={() => setSidebarOpen((value) => !value)}>History</button>
        <h2 id={threadTitleId}>{child.name}</h2><p>{child.age_label}</p>
      </header>
      <div className="chat-stage">
      <section className="conversation-thread" aria-labelledby={threadTitleId} ref={threadRef} tabIndex={0}>
        {chat.moreMessages && <button type="button" disabled={chat.busy} onClick={chat.loadOlderMessages}>Load earlier messages</button>}
        {chat.messages.map((message) => message.role === "user"
          ? <article className="caregiver-message" data-message-id={message.id} key={message.id}><h3>You</h3><p>{message.text}</p>
              {message.delivery === "cancelled" && <small role="status">Request cancelled.</small>}
              {message.delivery === "limited" && <small role="status">Please wait before sending another message.</small>}
              {message.delivery === "unconfirmed" && <small>Reopen this conversation to check for a reply before sending again.</small>}
            </article>
          : <GuidanceAnswer key={message.id} message={message} childName={child.name} allowFeedback={!readOnly}
              pending={message.pending === true}
              fresh={message.id === chat.newAnswerId} automaticPlayback={automatic} active={isActive && !chat.generating && !voiceBusy}
              conversationId={message.conversation_id === null ? null : chat.conversationId} />)}
        {!chat.messages.length && <div className="chat-welcome"><h3>What are you doing with your baby today?</h3>
          <p>Describe the moment, or ask for guidance.</p></div>}
        {chat.generating && <p className="guidance-loading" role="status"><span className="guidance-spinner" aria-hidden="true" />{chat.streamPhase === "saving" ? "Saving reply…" : chat.streamPhase === "writing" ? "Writing reply…" : "One moment…"}</p>}
      </section>
      {readOnly ? <p className="chat-composer">Read-only access: you can review or delete existing data. Accept the notice above to request coaching.</p> : <section className="question-panel chat-composer" aria-label="Message composer">
        <form onSubmit={submit}>
          <label className="visually-hidden" htmlFor={inputId}>Question</label>
          <textarea ref={composerRef} id={inputId} rows="1" value={question} readOnly={voiceBusy} maxLength={1200}
            onKeyDown={(event) => {
              if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing || event.keyCode === 229) return;
              event.preventDefault();
              if (!event.repeat) event.currentTarget.form?.requestSubmit();
            }}
            onChange={(event) => setQuestion(event.target.value)} placeholder="Type a message, or use the microphone…" />
          <details className="composer-options"><summary aria-label="Care options">＋</summary>
            <div className="composer-option-fields">
              <label htmlFor={routineId}>Routine (optional)</label>
              <select id={routineId} value={routine} onChange={(event) => setRoutine(event.target.value)}>
                <option value="">General caregiving</option><option value="feeding">Feeding</option><option value="bathing">Bathing</option>
                <option value="play">Play</option><option value="dressing">Dressing</option><option value="reading">Reading</option>
              </select>
            </div>
          </details>
          <div className="composer-actions">
            {isActive && <MicrophoneControls key={chat.conversationId || "new-chat"} compact onTranscriptChange={setQuestion}
              onCaptureStateChange={setVoiceBusy} disabled={chat.busy} />}
            {chat.generating ? <button type="button" className="send-message" aria-label="Stop waiting" title="Stop waiting" onClick={chat.cancelGeneration}>
              <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="1" /></svg>
            </button> : <button type="submit" className="send-message" aria-label="Get guidance" title="Send message" disabled={chat.busy || voiceBusy || question.trim().length < 2 || question.length > 1200}>
              <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5m-6 6 6-6 6 6" /></svg>
            </button>}
          </div>
          <p className="composer-help" aria-live="polite">{voiceBusy
            ? "Voice input in progress. Your words will appear here for review."
            : "Record up to 30 seconds. Review and edit your words here before sending."}</p>
        </form>
        {chat.error && <><p role="alert">{chat.error}</p>
          {chat.conversationId && <button type="button" disabled={chat.busy || voiceBusy}
            onClick={() => chat.open(chat.conversationId)}>Check for reply</button>}</>}
        <details className="conversation-privacy"><summary>Conversation privacy</summary>
          <p>Conversations and feedback stay in your history until you delete the conversation, its child profile, or your account.</p>
          <p>To answer follow-ups, recent messages from this conversation may be sent to the AI service. Reference search may include a recent caregiver message. Recorded audio is processed for transcription and is not deliberately saved by the application.</p>
        </details>
      </section>}
      </div>
    </div>
  </div>;
}

function Workspace({ processingAllowed, isActive, userId, initialChildren }) {
  const [knownChildren, setKnownChildren] = useState(initialChildren);
  const [reuseProfiles, setReuseProfiles] = useState(true);
  const rememberProfiles = useCallback((items) => {
    setKnownChildren(items); setReuseProfiles(true);
  }, []);
  useEffect(() => {
    if (knownChildren === undefined) return;
    // Expire selector reuse without discarding mounted child chats or drafts.
    const timer = setTimeout(() => setReuseProfiles(false), 60000);
    return () => clearTimeout(timer);
  }, [knownChildren]);
  const [child, setChild] = useState(null);
  const [busy, setBusy] = useState(false);
  const [visited, setVisited] = useState([]);
  const [routeStatus, setRouteStatus] = useState(() => readConversationLocation() ? { loading: true } : null);
  const [initialConversation, setInitialConversation] = useState(null);
  const controllers = useRef(new Map());
  const selectedChild = useRef(null);
  const handledRoute = useRef(null);
  const routeRequest = useRef(null);
  const register = useCallback((id, controller) => {
    if (controller) controllers.current.set(id, controller);
    else controllers.current.delete(id);
  }, []);
  const activateChild = useCallback((nextChild) => {
    stopGuidanceAudio(); setBusy(false); setChild(nextChild);
    selectedChild.current = nextChild;
    if (nextChild) setVisited((ids) => [...ids.filter((id) => id !== nextChild.id), nextChild.id].slice(-3));
  }, []);
  const navigate = useCallback((_childId, id, options) => {
    routeRequest.current?.abort();
    routeRequest.current = null;
    setInitialConversation(null);
    handledRoute.current = id;
    setConversationLocation(id, options);
    setRouteStatus(null);
  }, []);
  const selectChild = useCallback((nextChild) => {
    // The URL selects the initial profile; a selector's default must not replace it.
    if (!selectedChild.current && readConversationLocation() !== handledRoute.current) return;
    navigate(nextChild?.id, controllers.current.get(nextChild?.id)?.conversationId || null);
    activateChild(nextChild);
  }, [activateChild, navigate]);

  useEffect(() => {
    async function restoreLocation() {
      routeRequest.current?.abort();
      routeRequest.current = null;
      const id = readConversationLocation();
      if (!id) {
        setInitialConversation(null);
        handledRoute.current = null;
        controllers.current.get(selectedChild.current?.id)?.newChat({ navigate: false, force: true });
        if (!selectedChild.current && knownChildren?.[0]) activateChild(knownChildren[0]);
        setRouteStatus(null);
        return;
      }
      if (!knownChildren) return;
      // A cached child's currently open thread needs no second history request.
      const cachedChild = knownChildren.find(item => controllers.current.get(item.id)?.conversationId === id);
      if (cachedChild) {
        handledRoute.current = id; activateChild(cachedChild); setRouteStatus(null);
        return;
      }
      const controller = new AbortController();
      routeRequest.current = controller;
      const timer = setTimeout(() => controller.abort(), 8000);
      try {
        const conversation = await getConversation(id, null, controller.signal);
        if (controller.signal.aborted) return;
        const profile = knownChildren.find(item => item.id === conversation.child_id);
        if (!profile || conversation.id !== id || !Array.isArray(conversation.messages)) {
          throw new Error("This conversation is unavailable for this account.");
        }
        const existing = controllers.current.get(profile.id);
        if (existing) existing.restore(conversation);
        else setInitialConversation(conversation);
        handledRoute.current = id; activateChild(profile); setRouteStatus(null);
      } catch (cause) {
        if (routeRequest.current !== controller) return;
        setRouteStatus({ error: controller.signal.aborted ? "Conversation took too long to load. Please retry."
          : cause.status === 404 ? "This conversation is unavailable for this account." : cause.message });
      } finally { clearTimeout(timer); }
    }
    const onPopState = () => {
      stopGuidanceAudio();
      for (const controller of controllers.current.values()) controller.cancel();
      setRouteStatus(readConversationLocation() ? { loading: true } : null);
      void restoreLocation();
    };
    window.addEventListener("popstate", onPopState);
    if (readConversationLocation() && handledRoute.current !== readConversationLocation()) void restoreLocation();
    return () => {
      window.removeEventListener("popstate", onPopState);
      routeRequest.current?.abort(); routeRequest.current = null;
    };
  }, [knownChildren, activateChild]);

  const profileControls = <ChildProfiles userId={userId} selectedChild={child} onSelect={selectChild} guidanceBusy={busy} allowChanges={processingAllowed} isActive={isActive} initialChildren={reuseProfiles ? knownChildren : undefined} onProfilesChange={rememberProfiles} />;
  return <div className="guidance-workspace">
    {routeStatus && <section aria-label="Conversation access">
      {routeStatus.loading ? <p role="status">Loading conversation…</p> : <>
        <p role="alert">{routeStatus.error}</p>
        <button type="button" onClick={() => { setRouteStatus({ loading: true }); window.dispatchEvent(new PopStateEvent("popstate")); }}>Retry conversation</button>
        <button type="button" onClick={() => { setConversationLocation(null); window.dispatchEvent(new PopStateEvent("popstate")); }}>New chat</button>
      </>}
    </section>}
    {child ? (knownChildren || [child]).filter((item) => visited.includes(item.id)).map((item) =>
      <ConversationWorkspace key={item.id} child={item.id === child.id ? child : item} userId={userId}
        onNavigate={navigate} register={register} initialConversation={initialConversation?.child_id === item.id ? initialConversation : undefined}
        onBusyChange={setBusy} profileControls={item.id === child.id ? profileControls : null}
        readOnly={!processingAllowed} visible={item.id === child.id && !routeStatus} isActive={isActive && item.id === child.id && !routeStatus} />)
      : <div className="profile-onboarding" hidden={Boolean(routeStatus)}>{profileControls}<p>Select or add a child profile first.</p></div>}
  </div>;
}

export default function GuidanceWorkspace({ isActive = true, userId, startup }) {
  return <PrivacyConsent initialNotice={startup?.consent}>{(allowed, reuseInitialData) => <Workspace key={String(allowed)} processingAllowed={allowed} isActive={isActive} userId={userId}
    initialChildren={reuseInitialData ? startup?.children : undefined} />}</PrivacyConsent>;
}
