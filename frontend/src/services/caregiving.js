import { auth } from "./firebase";

async function request(path, options = {}) {
  options.signal?.throwIfAborted();
  const user = auth.currentUser;
  if (!user) throw new Error("Log in to continue.");
  const token = await user.getIdToken();
  options.signal?.throwIfAborted();
  if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${token}`, ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
  });
  options.signal?.throwIfAborted();
  if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
  const body = await response.json().catch(() => ({}));
  options.signal?.throwIfAborted();
  if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
  if (!response.ok) throw new Error(body.detail || "The request could not be completed.");
  return body;
}

export const listChildren = () => request("/children");
export const getPrivacyConsent = (signal) => request("/privacy/consent", { signal });
export const acceptPrivacyConsent = (version, signal) => request("/privacy/consent", {
  method: "POST", signal,
  body: JSON.stringify({ version, accepted: true, caregiver_authority: true }),
});
export const deleteChild = (id) => request(`/children/${encodeURIComponent(id)}`, { method: "DELETE" });
export const deleteAccount = () => request("/me", { method: "DELETE" });
export const createChild = (child) => request("/children", { method: "POST", body: JSON.stringify(child) });
export const updateChild = (id, child) => request(`/children/${id}`, { method: "PATCH", body: JSON.stringify(child) });
export async function requestCoaching(payload, { signal, timeoutMs = 60000 } = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort();
  if (signal?.aborted) cancel();
  signal?.addEventListener("abort", cancel, { once: true });
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    return await request("/coach", { method: "POST", body: JSON.stringify(payload), signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(`${timedOut ? "Guidance took too long." : "Stopped waiting for guidance."} The server may still save an answer; reopen this conversation before sending again.`, { cause: error });
    }
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}
export const sendFeedback = (interactionId, payload) => request(`/coach/${interactionId}/feedback`, { method: "POST", body: JSON.stringify(payload) });

export const createConversation = (childId, { signal } = {}) => request("/conversations", {
  method: "POST", body: JSON.stringify({ child_id: childId }), signal,
});
export const deleteConversation = (id) => request(`/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
export const listConversations = (childId, before = null) => {
  const query = new URLSearchParams({ child_id: childId, limit: "30" });
  if (before) query.set("before", before);
  return request(`/conversations?${query}`);
};
export const getConversation = (id, before = null) => {
  const query = new URLSearchParams({ limit: "50" });
  if (before) query.set("before", before);
  return request(`/conversations/${encodeURIComponent(id)}?${query}`);
};
