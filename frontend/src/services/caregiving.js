import { auth } from "./firebase";
import { readCoachingStream } from "./coachingStream";

const REQUEST_ERROR = "Something went wrong. Please try again.";

async function request(path, options = {}, onStreamEvent) {
  options.signal?.throwIfAborted();
  const user = auth.currentUser;
  if (!user) throw new Error("Log in to continue.");
  const token = await user.getIdToken();
  options.signal?.throwIfAborted();
  if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
  let response;
  try {
    response = await fetch(`/api${path}`, {
    ...options,
    credentials: "omit",
    cache: "no-store",
    headers: { Authorization: `Bearer ${token}`, ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
    });
  } catch (cause) {
    if (options.signal?.aborted) throw cause;
    throw new Error(REQUEST_ERROR, { cause });
  }
  options.signal?.throwIfAborted();
  if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
  if (response.ok && response.headers?.get("Content-Type")?.toLowerCase().startsWith("text/event-stream")) {
    return readCoachingStream(response, {
      check: () => {
        options.signal?.throwIfAborted();
        if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
      },
      onEvent: (event) => {
        if (event.type === "ready") validateCoachingResponse(event.response);
        onStreamEvent?.(event);
      },
    });
  }
  const body = await response.json().catch(() => ({}));
  options.signal?.throwIfAborted();
  if (auth.currentUser !== user) throw new Error("Account changed. Please try again.");
  if (!response.ok) {
    if (response.headers?.get("X-Consent-Required") === "true") {
      window.dispatchEvent(new Event("privacy-consent-required"));
    }
    const detail = response.status >= 500 ? REQUEST_ERROR
      : typeof body.detail === "string" ? body.detail : REQUEST_ERROR;
    const retryHeader = response.headers?.get("Retry-After");
    const seconds = /^\d+$/.test(retryHeader || "") ? Number(retryHeader) : NaN;
    const retryAfter = response.status === 429 && Number.isSafeInteger(seconds) && seconds > 0 ? seconds : null;
    let message = detail;
    if (retryAfter) {
      const unit = retryAfter >= 3600 ? "hour" : retryAfter >= 60 ? "minute" : "second";
      const amount = Math.ceil(retryAfter / (unit === "hour" ? 3600 : unit === "minute" ? 60 : 1));
      message += ` Please try again in ${amount} ${unit}${amount === 1 ? "" : "s"}.`;
    }
    const error = new Error(message);
    error.status = response.status;
    error.retryAfterSeconds = retryAfter;
    throw error;
  }
  return body;
}

export const listChildren = (signal) => request("/children", { signal });
export const getAccountSecurity = () => request("/me/security");
export const disableAccountMfa = () => request("/me/security/mfa/disable", { method: "POST" });
export const getFeedbackSummary = (signal) => request("/admin/feedback/summary", { signal });
export const getPrivacyConsent = (signal) => request("/privacy/consent", { signal });
export const acceptPrivacyConsent = (version, signal) => request("/privacy/consent", {
  method: "POST", signal,
  body: JSON.stringify({ version, accepted: true, caregiver_authority: true }),
});
export const deleteChild = (id) => request(`/children/${encodeURIComponent(id)}`, { method: "DELETE" });
export const deleteAccount = () => request("/me", { method: "DELETE" });
export const deleteMyData = () => request("/me/data", { method: "DELETE" });
export const createChild = (child) => request("/children", { method: "POST", body: JSON.stringify(child) });
export const updateChild = (id, child) => request(`/children/${id}`, { method: "PATCH", body: JSON.stringify(child) });

function validateCoachingResponse(value) {
  const object = item => item !== null && typeof item === "object" && !Array.isArray(item);
  const text = item => typeof item === "string" && item.trim().length > 0;
  const number = item => typeof item === "number" && Number.isFinite(item) && item >= 0;
  const id = item => item == null || (text(item) && item.length <= 128 && !item.includes("/"));
  const link = (item, telephone = false) => {
    if (!text(item)) return false;
    try { return ["https:", "http:", ...(telephone ? ["tel:"] : [])].includes(new URL(item).protocol); }
    catch { return false; }
  };
  const statuses = ["answered", "no_evidence", "safety_blocked", "escalated", "crisis_support", "caregiver_support", "vaccination_notice"];
  const kinds = ["clarification", "unrelated", "professional_referral", "insufficient_references", "age_out_of_scope", "unsupported_language"];
  const valid = object(value) && text(value.answer) && statuses.includes(value.status)
    && ["not_flagged", "escalate"].includes(value.safety)
    && number(value.processing_seconds) && number(value.child_age_months)
    && (value.status !== "answered" || value.child_age_months <= 24)
    && (value.answer_basis == null || ["reference_assisted", "general_information"].includes(value.answer_basis))
    && (value.reference_status == null || ["matched", "no_match", "unavailable"].includes(value.reference_status))
    && id(value.interaction_id) && id(value.conversation_id) && id(value.message_id)
    && (value.response_kind == null || kinds.includes(value.response_kind))
    && (value.vaccination_country == null || value.vaccination_country === "KE")
    && Array.isArray(value.citations) && value.citations.every(item => object(item)
      && text(item.passage_id) && text(item.source_title) && text(item.title) && link(item.source_url)
      && (item.pdf_page === null || (Number.isInteger(item.pdf_page) && item.pdf_page > 0)))
    && (value.status !== "answered" || value.citations.length > 0 || value.answer_basis === "general_information")
    && (value.support_resources === undefined || (Array.isArray(value.support_resources)
      && value.support_resources.every(item => object(item) && text(item.label) && text(item.service)
        && item.country === "KE" && text(item.availability) && text(item.verified_on)
        && link(item.url, true) && link(item.source_url))));
  if (!valid) throw new Error("Something went wrong. Reopen this conversation to check for a reply before sending again.");
  return value;
}

export async function requestCoaching(payload, { signal, timeoutMs = 60000, onEvent } = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort();
  if (signal?.aborted) cancel();
  signal?.addEventListener("abort", cancel, { once: true });
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await request("/coach", { method: "POST", body: JSON.stringify(payload), signal: controller.signal,
      headers: { Accept: "text/event-stream" } }, onEvent);
    return validateCoachingResponse(response);
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(`${timedOut ? "This is taking longer than expected." : "Request cancelled."} Reopen this conversation to check for a reply before sending again.`, { cause: error });
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
export const listConversations = (childId, before = null, signal) => {
  const query = new URLSearchParams({ child_id: childId, limit: "30" });
  if (before) query.set("before", before);
  return request(`/conversations?${query}`, { signal });
};
export const getConversation = (id, before = null, signal) => {
  const query = new URLSearchParams({ limit: "50" });
  if (before) query.set("before", before);
  return request(`/conversations/${encodeURIComponent(id)}?${query}`, { signal });
};
