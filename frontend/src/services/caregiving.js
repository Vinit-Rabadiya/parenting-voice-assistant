import { auth } from "./firebase";

async function request(path, options = {}) {
  const user = auth.currentUser;
  if (!user) throw new Error("Log in to continue.");
  const token = await user.getIdToken();
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${token}`, ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "The request could not be completed.");
  return body;
}

export const listChildren = () => request("/children");
export const createChild = (child) => request("/children", { method: "POST", body: JSON.stringify(child) });
export const updateChild = (id, child) => request(`/children/${id}`, { method: "PATCH", body: JSON.stringify(child) });
export const requestCoaching = (payload) => request("/coach", { method: "POST", body: JSON.stringify(payload) });
export const sendFeedback = (interactionId, payload) => request(`/coach/${interactionId}/feedback`, { method: "POST", body: JSON.stringify(payload) });
