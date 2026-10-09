import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { transcribeAudio } from "../../frontend/src/services/transcription";

const { auth } = vi.hoisted(() => ({ auth: { currentUser: null } }));
vi.mock("../../frontend/src/services/firebase", () => ({ auth }));

const validResult = { text: "My baby is six months old.", audio_seconds: 1, processing_seconds: 0.2 };

beforeEach(() => {
  auth.currentUser = { getIdToken: vi.fn().mockResolvedValue("test-token") };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => validResult }));
});
afterEach(() => vi.unstubAllGlobals());

describe("speech api client", () => {
  // the exact blob and current login token must reach the existing endpoint.
  it("sends raw wav bytes with authentication and cancellation", async () => {
    const blob = new Blob(["audio"], { type: "audio/wav" });
    const controller = new AbortController();
    expect(await transcribeAudio(blob, controller.signal)).toEqual(validResult);
    expect(fetch).toHaveBeenCalledWith("/api/speech/transcribe", expect.objectContaining({
      method: "POST", body: blob, signal: controller.signal, credentials: "omit",
      headers: { Authorization: "Bearer test-token", "Content-Type": "audio/wav" },
    }));
  });

  it("rejects signed-out users without uploading", async () => {
    auth.currentUser = null;
    await expect(transcribeAudio(new Blob())).rejects.toThrow("Log in");
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each(["cancel", "account change"])("does not upload after %s during token retrieval", async (action) => {
    const controller = new AbortController();
    auth.currentUser.getIdToken.mockImplementation(async () => {
      if (action === "cancel") controller.abort();
      else auth.currentUser = null;
      return "token";
    });
    await expect(transcribeAudio(new Blob(), controller.signal)).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([401, 403, 413, 415, 422, 429, 503])("reports backend error %i without retrying", async (status) => {
    fetch.mockResolvedValue({ ok: false, status, json: async () => ({ detail: `failure ${status}` }) });
    await expect(transcribeAudio(new Blob())).rejects.toThrow(`failure ${status}`);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("reports non-json responses and preserves the parsing cause", async () => {
    const cause = new SyntaxError("html response");
    fetch.mockResolvedValue({ ok: false, json: async () => { throw cause; } });
    await expect(transcribeAudio(new Blob())).rejects.toMatchObject({
      message: expect.stringContaining("unreadable"), cause,
    });
  });

  it("rejects malformed successful data", async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => ({ text: 42 }) });
    await expect(transcribeAudio(new Blob())).rejects.toThrow("unexpected result");
  });

  it("ignores account changes while reading the body", async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => {
      auth.currentUser = null;
      return validResult;
    } });
    await expect(transcribeAudio(new Blob())).rejects.toThrow("Account changed");
  });

  it("reports network failure", async () => {
    fetch.mockRejectedValue(new TypeError("network unavailable"));
    await expect(transcribeAudio(new Blob())).rejects.toThrow("Could not reach");
  });
});
