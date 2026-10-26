import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { requestCoaching } from "../../frontend/src/services/caregiving";
import { auth } from "../../frontend/src/services/firebase";

vi.mock("../../frontend/src/services/firebase", () => ({ auth: { currentUser: null } }));

const validResponse = { answer: "Talk softly.", status: "answered", safety: "not_flagged",
  child_age_months: 6, processing_seconds: 1, interaction_id: "answer-1",
  citations: [{ passage_id: "p1", source_title: "Reference", title: "Talking",
    source_url: "https://example.test/reference", pdf_page: 1 }] };

it("shows the server retry interval without automatically retrying", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: false, status: 429,
    headers: new Headers({ "Retry-After": "65" }),
    json: async () => ({ detail: "Hourly request limit reached." }),
  });
  vi.stubGlobal("fetch", fetch);
  await expect(requestCoaching({ question: "Play ideas" })).rejects.toMatchObject({
    status: 429, retryAfterSeconds: 65,
    message: "Hourly request limit reached. Please try again in 2 minutes.",
  });
  expect(fetch).toHaveBeenCalledTimes(1);
});

beforeEach(() => {
  auth.currentUser = { getIdToken: vi.fn().mockResolvedValue("test-token") };
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

function pendingFetch() {
  const fetch = vi.fn((_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
  }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

it("times out one coaching request without retrying", async () => {
  vi.useFakeTimers();
  const fetch = pendingFetch();
  const result = requestCoaching({ question: "Feeding ideas" }, { timeoutMs: 60 });
  const assertion = expect(result).rejects.toThrow("Guidance took too long.");
  await vi.advanceTimersByTimeAsync(60);
  await assertion;
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});

it("cancels an active coaching request and warns about server completion", async () => {
  const fetch = pendingFetch();
  const controller = new AbortController();
  const result = requestCoaching({ question: "Feeding ideas" }, { signal: controller.signal });
  const assertion = expect(result).rejects.toThrow("The server may still save an answer");
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  controller.abort();
  await assertion;
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("does not send an already cancelled request", async () => {
  const fetch = pendingFetch();
  const controller = new AbortController();
  controller.abort();
  await expect(requestCoaching({}, { signal: controller.signal })).rejects.toThrow("Stopped waiting");
  expect(fetch).not.toHaveBeenCalled();
});

it("returns successful responses and clears the deadline", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true,
    json: async () => validResponse }));
  await expect(requestCoaching({ question: "Feeding ideas" })).resolves.toEqual(validResponse);
  expect(vi.getTimerCount()).toBe(0);
});

it.each([
  { answer: " " }, { status: "unknown" }, { processing_seconds: -1 },
  { citations: [] }, { citations: "invalid" }, { support_resources: {} },
])("rejects malformed guidance without retrying: %j", async (change) => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...validResponse, ...change }) });
  vi.stubGlobal("fetch", fetch);
  await expect(requestCoaching({ question: "Feeding ideas" })).rejects.toThrow("response could not be read");
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("accepts a fixed urgent response for an older child without citations", async () => {
  const response = { ...validResponse, status: "escalated", safety: "escalate", child_age_months: 25, citations: [] };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => response }));
  await expect(requestCoaching({})).resolves.toEqual(response);
});

it("accepts explicitly labelled general information at 24 months without citations", async () => {
  const response = { ...validResponse, child_age_months: 24, citations: [],
    answer_basis: "general_information", reference_status: "no_match" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => response }));
  await expect(requestCoaching({})).resolves.toEqual(response);
});

it("rejects generated guidance beyond 24 months but accepts an age-range notice", async () => {
  const response = { ...validResponse, child_age_months: 25, citations: [], answer_basis: "general_information" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => response }));
  await expect(requestCoaching({})).rejects.toThrow("response could not be read");
  const notice = { ...response, status: "no_evidence", response_kind: "age_out_of_scope" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => notice }));
  await expect(requestCoaching({})).resolves.toEqual(notice);
});

it("rejects a response after the signed-in account changes", async () => {
  vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => {
    auth.currentUser = null;
    return { ok: true, json: async () => ({ answer: "Private answer" }) };
  }));
  await expect(requestCoaching({})).rejects.toThrow("Account changed");
});

it("invalidates cached consent when a protected request requires a new acceptance", async () => {
  const required = vi.fn();
  window.addEventListener("privacy-consent-required", required);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false,
    headers: new Headers({ "X-Consent-Required": "true" }),
    json: async () => ({ detail: "Review the privacy notice." }),
  }));
  try {
    await expect(requestCoaching({})).rejects.toThrow("Review the privacy notice.");
    expect(required).toHaveBeenCalledTimes(1);
  } finally { window.removeEventListener("privacy-consent-required", required); }
});
