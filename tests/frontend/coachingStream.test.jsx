import { ReadableStream } from "node:stream/web";
import { TextEncoder } from "node:util";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readCoachingStream } from "../../frontend/src/services/coachingStream";
import { requestCoaching } from "../../frontend/src/services/caregiving";
import { auth } from "../../frontend/src/services/firebase";

vi.mock("../../frontend/src/services/firebase", () => ({ auth: { currentUser: null } }));
const answer = { answer: "Talk gently with bébé.", status: "answered", safety: "not_flagged", child_age_months: 6,
  processing_seconds: 2, answer_basis: "general_information", citations: [], conversation_id: "chat-1", message_id: "answer-1" };
const frame = (type, data) => `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`;
function response(wire) {
  const bytes = new TextEncoder().encode(wire);
  return { ok: true, headers: new Headers({ "Content-Type": "text/event-stream" }), body: new ReadableStream({
    start(controller) { for (const byte of bytes) controller.enqueue(Uint8Array.of(byte)); controller.close(); },
  }) };
}
beforeEach(() => { auth.currentUser = { getIdToken: vi.fn().mockResolvedValue("token") }; });
afterEach(() => { vi.unstubAllGlobals(); });

it("decodes split UTF-8 characters and SSE frames without losing text", async () => {
  const seen = [];
  const wire = frame("status", { phase: "writing" }) + ": keep-alive\n\n"
    + frame("delta", { text: "Talk gently with bébé. " })
    + frame("ready", { response: answer }) + frame("done", { response: answer });
  expect(await readCoachingStream(response(wire), { onEvent: event => seen.push(event) })).toEqual(answer);
  expect(seen.map(event => event.type)).toEqual(["status", "delta", "ready"]);
  expect(seen[1].text).toBe("Talk gently with bébé. ");
});

it("rejects an interrupted stream instead of accepting partial text", async () => {
  await expect(readCoachingStream(response(frame("delta", { text: "Partial. " })))).rejects.toThrow("interrupted");
});

it("delivers a reset between previews when the server switches providers", async () => {
  const seen = [];
  const wire = frame("delta", { text: "Old preview. " }) + frame("reset", {})
    + frame("delta", { text: "Backup answer. " }) + frame("done", { response: answer });
  await readCoachingStream(response(wire), { onEvent: event => seen.push(event) });
  expect(seen.map(event => event.type)).toEqual(["delta", "reset", "delta"]);
});

it("rejects malformed events and oversized frames", async () => {
  await expect(readCoachingStream(response("event: delta\ndata: not-json\n\n"))).rejects.toThrow();
  await expect(readCoachingStream(response(frame("delta", { text: "x".repeat(65536) })))).rejects.toThrow("interrupted");
});

it("requests one stream and returns only its validated final response", async () => {
  const onEvent = vi.fn();
  const fetch = vi.fn().mockResolvedValue(response(frame("delta", { text: "Talk gently. " })
    + frame("ready", { response: answer }) + frame("done", { response: answer })));
  vi.stubGlobal("fetch", fetch);
  expect(await requestCoaching({ question: "Babbling ideas?" }, { onEvent })).toEqual(answer);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][1].headers.Accept).toBe("text/event-stream");
  expect(onEvent).toHaveBeenCalledTimes(2);
});

it("does not expose internal errors or accept a final response after stream failure", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(frame("error", { status: 503, detail: "PRIVATE_STORAGE" }))));
  await expect(requestCoaching({ question: "Babbling ideas?" })).rejects.toMatchObject({ status: 503, message: "Something went wrong. Please try again." });
});

it("rejects an invalid ready answer before displaying it", async () => {
  const onEvent = vi.fn();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(frame("ready", { response: { answer: "Invalid" } }))));
  await expect(requestCoaching({ question: "Babbling ideas?" }, { onEvent })).rejects.toThrow();
  expect(onEvent).not.toHaveBeenCalled();
});

it("stops delivering events when the signed-in account changes", async () => {
  const onEvent = vi.fn(() => { auth.currentUser = null; });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(frame("delta", { text: "Talk gently. " })
    + frame("delta", { text: "Pause. " }) + frame("done", { response: answer }))));
  await expect(requestCoaching({ question: "Babbling ideas?" }, { onEvent })).rejects.toThrow("Account changed");
  expect(onEvent).toHaveBeenCalledTimes(1);
});
