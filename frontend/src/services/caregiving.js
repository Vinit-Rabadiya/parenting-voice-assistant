import { auth } from "./firebase";

async function request(path, options = {}) {
  const user = auth.currentUser;
  if (!user) throw new Error("Log in to continue.");
  const token = await user.getIdToken();
  if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${token}`, ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
  if (!response.ok) throw new Error(body.detail || "The request could not be completed.");
  return body;
}

export const listChildren = () => request("/children");
export const deleteChild = (id) => request(`/children/${encodeURIComponent(id)}`, { method: "DELETE" });
export const deleteAccount = () => request("/me", { method: "DELETE" });
export const createChild = (child) => request("/children", { method: "POST", body: JSON.stringify(child) });
export const updateChild = (id, child) => request(`/children/${id}`, { method: "PATCH", body: JSON.stringify(child) });
export const requestCoaching = (payload) => request("/coach", { method: "POST", body: JSON.stringify(payload) });
export const sendFeedback = (interactionId, payload) => request(`/coach/${interactionId}/feedback`, { method: "POST", body: JSON.stringify(payload) });

export const createConversation = (childId) => request("/conversations", {
  method: "POST", body: JSON.stringify({ child_id: childId }),
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
