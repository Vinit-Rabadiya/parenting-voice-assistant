import { useEffect, useRef, useState } from "react";
import { createConversation, deleteConversation, getConversation, listConversations, requestCoaching } from "../services/caregiving";

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

  useEffect(() => {
    mounted.current = true;
    let active = true;
    listConversations(childId).then((items) => {
      if (!active) return;
      setConversations(items);
      setMoreConversations(items.length === 30);
    }).catch((cause) => active && setHistoryError(cause.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; mounted.current = false; coachingRequest.current?.abort(); window.speechSynthesis?.cancel(); };
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
    window.speechSynthesis?.cancel();
    setConversationId(null); setMessages([]); setMoreMessages(false); setError("");
  }

  function open(id) {
    window.speechSynthesis?.cancel();
    return perform(async () => {
      const item = await getConversation(id);
      if (!mounted.current) return;
      setConversationId(id); setMessages(item.messages); setMoreMessages(item.messages.length === 50);
    });
  }

  function submit(question, routine, supportCountry) {
    if (locked.current) return Promise.resolve(false);
    return perform(async () => {
      const controller = new AbortController();
      coachingRequest.current = controller;
      setGenerating(true);
      const localId = crypto.randomUUID();
      const questionId = `question-${localId}`;
      setMessages((items) => [...items, { id: questionId, role: "user", text: question, delivery: "pending" }]);
      try {
        let id = conversationId;
        if (!id) {
          const item = await createConversation(childId, { signal: controller.signal });
          if (!mounted.current) return;
          id = item.id; setConversationId(id); setConversations((items) => [item, ...items]);
        }
        controller.signal.throwIfAborted();
        const response = await requestCoaching({ child_id: childId, conversation_id: id,
          question, routine: routine || null, support_country: supportCountry || null }, { signal: controller.signal });
        if (!mounted.current) return;
        setMessages((items) => [...items.map((item) => item.id === questionId ? { ...item, delivery: "sent" } : item),
          { ...response, id: response.message_id || localId, message_id: response.message_id ?? null,
            role: "assistant", text: response.answer },
        ]);
        setConversations((items) => {
          const current = items.find((item) => item.id === id);
          return current ? [{ ...current, title: current.title === "New conversation" ? question.slice(0, 80) : current.title },
            ...items.filter((item) => item.id !== id)] : items;
        });
      } catch (cause) {
        if (mounted.current) setMessages((items) => items.map((item) => item.id === questionId
          ? { ...item, delivery: controller.signal.aborted ? "cancelled" : cause.status === 429 ? "limited" : "unconfirmed" } : item));
        if (controller.signal.aborted) throw new Error("Request cancelled in this browser. The server may still save an answer; reopen the conversation before sending again.", { cause });
        throw cause;
      } finally {
        coachingRequest.current = null;
        if (mounted.current) setGenerating(false);
      }
    });
  }

  function remove(id) {
    if (!id || locked.current || !window.confirm("Delete this conversation and its messages and feedback? This cannot be undone.")) return;
    if (id === conversationId) window.speechSynthesis?.cancel();
    return perform(async () => {
      await deleteConversation(id);
      if (!mounted.current) return;
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
        return [...items, ...page.filter((item) => !ids.has(item.id))];
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

  return { conversations, conversationId, messages, busy, generating,
    cancelGeneration, loading, error, historyError,
    moreConversations, moreMessages, newChat, open, submit, remove, loadOlderMessages, loadOlderConversations };
}
