// Conversation URLs contain opaque IDs only; API ownership checks remain authoritative.
const conversationPath = /^\/chat\/([A-Za-z0-9_-]{1,128})\/?$/;

export function readConversationLocation() {
  return window.location.pathname.match(conversationPath)?.[1] || null;
}

export function setConversationLocation(id, { replace = false } = {}) {
  if (id !== null && !/^[A-Za-z0-9_-]{1,128}$/.test(id)) return;
  const path = id ? `/chat/${id}` : "/";
  if (window.location.pathname === path) return;
  // pushState does not reload the app or emit popstate for an already-open chat.
  window.history[replace ? "replaceState" : "pushState"](null, "", path);
}
