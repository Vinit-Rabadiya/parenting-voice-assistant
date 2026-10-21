import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { requestCoaching } from "../../frontend/src/services/caregiving";
import { auth } from "../../frontend/src/services/firebase";

vi.mock("../../frontend/src/services/firebase", () => ({ auth: { currentUser: null } }));

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
    json: async () => ({ answer: "Talk softly." }) }));
  await expect(requestCoaching({ question: "Feeding ideas" })).resolves.toEqual({ answer: "Talk softly." });
  expect(vi.getTimerCount()).toBe(0);
});

it("rejects a response after the signed-in account changes", async () => {
  vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => {
    auth.currentUser = null;
    return { ok: true, json: async () => ({ answer: "Private answer" }) };
  }));
  await expect(requestCoaching({})).rejects.toThrow("Account changed");
});
