import { useEffect, useRef, useState } from "react";
import { deleteConversation, getConversation, listConversations, requestCoaching } from "../services/caregiving";
import { stopGuidanceAudio } from "./useGuidanceAudio";

export default function useConversations(childId, onBusyChange) {
  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [moreConversations, setMoreConversations] = useState(false);
  const [moreMessages, setMoreMessages] = useState(false);
  const mounted = useRef(false);
  const locked = useRef(false);
  const coachingRequest = useRef(null);
  const [generating, setGenerating] = useState(false);
  const [newAnswerId, setNewAnswerId] = useState(null);
  const removedIds = useRef(new Set());
  const unconfirmedConversation = useRef(null);

  useEffect(() => {
    mounted.current = true;
    let active = true;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    listConversations(childId, null, controller.signal).then((items) => {
      if (!active) return;
      setConversations((current) => {
        const ids = new Set(current.map((item) => item.id));
        return [...current, ...items.filter((item) => !ids.has(item.id) && !removedIds.current.has(item.id))];
      });
      setMoreConversations(items.length === 30);
    }).catch((cause) => active && setHistoryError(controller.signal.aborted ? "History took too long to load. Please retry." : cause.message))
      .finally(() => { clearTimeout(timer); if (active) setLoading(false); });
    return () => { active = false; clearTimeout(timer); controller.abort(); mounted.current = false; coachingRequest.current?.abort(); stopGuidanceAudio(); };
  }, [childId]);

  async function perform(action) {
    if (locked.current) return false;
    locked.current = true;
    setBusy(true); onBusyChange(true); setError("");
    try { await action(); return mounted.current; }
    catch (cause) { if (mounted.current) setError(cause.message); return false; }
    finally {
      locked.current = false;
      if (mounted.current) { setBusy(false); onBusyChange(false); }
    }
  }

  function newChat() {
    if (locked.current) return;
    stopGuidanceAudio(); setNewAnswerId(null);
    unconfirmedConversation.current = null;
    setConversationId(null); setMessages([]); setMoreMessages(false); setError("");
  }

  function open(id) {
    stopGuidanceAudio(); setNewAnswerId(null);
    return perform(async () => {
      const item = await getConversation(id);
      if (!mounted.current) return;
      unconfirmedConversation.current = null;
      setConversationId(id); setMessages(item.messages); setMoreMessages(item.messages.length === 50);
    });
  }

  function submit(question, routine, supportCountry) {
    if (locked.current) return Promise.resolve(false);
    return perform(async () => {
      const controller = new AbortController();
      coachingRequest.current = controller;
      setNewAnswerId(null);
      setGenerating(true);
      const localId = crypto.randomUUID();
      const questionId = `question-${localId}`;
      setMessages((items) => [...items, { id: questionId, role: "user", text: question, delivery: "pending" }]);
      try {
        let firstMessage = !conversationId;
        const id = conversationId || crypto.randomUUID();
        if (unconfirmedConversation.current === id) {
          try {
            await getConversation(id, null, controller.signal);
            controller.signal.throwIfAborted();
            unconfirmedConversation.current = null;
          } catch (cause) {
            controller.signal.throwIfAborted();
            if (cause.status !== 404) throw cause;
            firstMessage = true;
          }
        }
        if (firstMessage) {
          unconfirmedConversation.current = id;
          setConversationId(id);
        }
        controller.signal.throwIfAborted();
        const response = await requestCoaching({ child_id: childId, conversation_id: id,
          question, routine: routine || null, support_country: supportCountry || null,
          ...(firstMessage ? { start_conversation: true } : {}) }, { signal: controller.signal });
        controller.signal.throwIfAborted();
        if (!mounted.current) return;
        unconfirmedConversation.current = null;
        setNewAnswerId(response.message_id || localId);
        setMessages((items) => [...items.map((item) => item.id === questionId ? { ...item, delivery: "sent" } : item),
          { ...response, id: response.message_id || localId, message_id: response.message_id ?? null,
            role: "assistant", text: response.answer },
        ]);
        setConversations((items) => {
          const current = items.find((item) => item.id === id) || { id, child_id: childId, title: "New conversation" };
          return [{ ...current, title: current.title === "New conversation" ? question.slice(0, 80) : current.title },
            ...items.filter((item) => item.id !== id)];
        });
      } catch (cause) {
        if (mounted.current) setMessages((items) => items.map((item) => item.id === questionId
          ? { ...item, delivery: controller.signal.aborted ? "cancelled" : cause.status === 429 ? "limited" : "unconfirmed" } : item));
        if (controller.signal.aborted) throw new Error("Request cancelled. Reopen this conversation to check for a reply before sending again.", { cause });
        throw cause;
      } finally {
        coachingRequest.current = null;
        if (mounted.current) setGenerating(false);
      }
    });
  }

  function remove(id) {
    if (!id || locked.current || !window.confirm("Delete this conversation and its messages and feedback? This cannot be undone.")) return;
    if (id === conversationId) { stopGuidanceAudio(); setNewAnswerId(null); }
    return perform(async () => {
      await deleteConversation(id);
      if (!mounted.current) return;
      removedIds.current.add(id);
      setConversations((items) => items.filter((item) => item.id !== id));
      if (id === conversationId) {
        setConversationId(null); setMessages([]); setMoreMessages(false);
      }
    });
  }

  function loadOlderMessages() {
    return perform(async () => {
      const page = await getConversation(conversationId, messages[0].id);
      if (!mounted.current) return;
      setMessages((items) => [...page.messages, ...items]); setMoreMessages(page.messages.length === 50);
    });
  }

  function loadOlderConversations() {
    return perform(async () => {
      const page = await listConversations(childId, historyError ? null : conversations.at(-1)?.id);
      if (!mounted.current) return;
      setHistoryError("");
      setConversations((items) => {
        const ids = new Set(items.map((item) => item.id));
        return [...items, ...page.filter((item) => !ids.has(item.id) && !removedIds.current.has(item.id))];
      });
      setMoreConversations(page.length === 30);
    });
  }

  function cancelGeneration() {
    if (!coachingRequest.current || coachingRequest.current.signal.aborted) return;
    setMessages((items) => items.map((item) => item.delivery === "pending"
      ? { ...item, delivery: "cancelled" } : item));
    coachingRequest.current.abort();
  }

  return { conversations, conversationId, messages, busy, generating, newAnswerId,
    cancelGeneration, loading, error, historyError,
    moreConversations, moreMessages, newChat, open, submit, remove, loadOlderMessages, loadOlderConversations };
}
