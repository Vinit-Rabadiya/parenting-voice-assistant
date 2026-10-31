import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import vm from "node:vm";
import { Blob as NodeBlob } from "node:buffer";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import GuidanceWorkspace from "../../frontend/src/components/GuidanceWorkspace";
import usePlaybackPreference from "../../frontend/src/hooks/usePlaybackPreference";

vi.mock("../../frontend/src/services/firebase", () => ({
  auth: { currentUser: { uid: "workflow-account", getIdToken: async () => "workflow-token" } },
}));

const nativeFetch = globalThis.fetch;
const root = existsSync(join(process.cwd(), "backend/main.py")) ? process.cwd() : resolve(process.cwd(), "..");
let server, base, serverOutput = "", requests;
beforeAll(async () => {
  const python = process.platform === "win32" ? "venv/Scripts/python.exe" : "venv/bin/python";
  server = spawn(existsSync(join(root, python)) ? join(root, python) : "python", ["tests/workflow_app.py"], {
    cwd: root,
    windowsHide: true, env: { ...process.env, FIREBASE_PROJECT_ID: "test-project" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  server.stdout.on("data", (data) => { serverOutput += data; });
  server.stderr.on("data", (data) => { serverOutput += data; });
  await waitFor(() => {
    const port = serverOutput.match(/WORKFLOW_PORT=(\d+)/)?.[1];
    expect(port, serverOutput).toBeTruthy();
    base = `http://127.0.0.1:${port}`;
  }, { timeout: 20000 });
  await waitFor(async () => expect((await nativeFetch(`${base}/__workflow/ready`)).ok).toBe(true), { timeout: 10000 });
}, 35000);
afterAll(() => server?.kill());

beforeEach(async () => {
  await nativeFetch(`${base}/__workflow/reset`, { method: "POST" });
  requests = [];
  localStorage.clear();
  vi.stubGlobal("Blob", NodeBlob);
  vi.stubGlobal("fetch", async (path, options) => {
    requests.push({ path, ...options });
    return nativeFetch(new URL(path.replace(/^\/api/, ""), base), options);
  });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.stubGlobal("SpeechSynthesisUtterance", function (text) { this.text = text; });
  vi.stubGlobal("speechSynthesis", {
    cancel: vi.fn(), speak: vi.fn((utterance) => queueMicrotask(() => utterance.onstart?.())),
  });
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
  const track = { stop: vi.fn() };
  Object.defineProperty(navigator, "mediaDevices", { configurable: true,
    value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [track] })) } });
  vi.stubGlobal("AudioContext", class {
    sampleRate = 16000;
    state = "running";
    destination = {};
    audioWorklet = { addModule: async () => {} };
    resume = async () => {};
    close = async () => { this.state = "closed"; };
    createMediaStreamSource = () => ({ connect() {}, disconnect() {} });
  });
  vi.stubGlobal("AudioWorkletNode", class {
    constructor() {
      let Processor;
      const node = this;
      this.port = { onmessage: null, close() {}, postMessage(data) { node.processor.port.onmessage({ data }); } };
      vm.runInNewContext(readFileSync(join(root, "frontend/public/audio/capture.worklet.js"), "utf8"), {
        Float32Array,
        AudioWorkletProcessor: class { constructor() { this.port = { postMessage: (data) => queueMicrotask(() => node.port.onmessage?.({ data })) }; } },
        registerProcessor: (_, implementation) => { Processor = implementation; },
      });
      this.processor = new Processor();
      queueMicrotask(() => this.processor.process([[new Float32Array(16000).fill(0.1)]]));
    }
    connect() {}
    disconnect() {}
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function openWorkspace() {
  render(<GuidanceWorkspace userId="workflow-account" />);
  return screen.findByRole("textbox", { name: "Question" });
}

it("uses the saved account playback choice without disabling manual Listen", async () => {
  const preference = renderHook(() => usePlaybackPreference("workflow-account"));
  act(() => preference.result.current.setAutomatic(false));
  const input = await openWorkspace();
  fireEvent.change(input, { target: { value: "How can I talk while dressing?" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await screen.findByText("Talk gently while dressing.");
  // Flush the zero-delay automatic-playback effect after the answer is rendered.
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  expect(speechSynthesis.speak).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  await waitFor(() => expect(speechSynthesis.speak).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: "Stop audio" }));
  expect(screen.getByRole("button", { name: "Listen" })).toBeTruthy();
});

it("records, edits, sends, plays, saves feedback, restores history and deletes through the API", async () => {
  const input = await openWorkspace();
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  fireEvent.click(await screen.findByRole("button", { name: "Cancel recording" }));
  await screen.findByRole("button", { name: "Start recording" });
  expect(requests.some((r) => r.path === "/api/speech/transcribe")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  await screen.findByRole("button", { name: "Pause recording" });
  fireEvent.click(screen.getByRole("button", { name: "Pause recording" }));
  fireEvent.click(await screen.findByRole("button", { name: "Resume recording" }));
  fireEvent.click(screen.getByRole("button", { name: "Stop and transcribe" }));
  await waitFor(() => expect(input.value).toBe("I am dressing my baby."));
  const edited = "I am dressing my baby. How can I talk with her?";
  fireEvent.change(input, { target: { value: edited } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(input.value).toBe("");
  await screen.findByText("Talk gently while dressing.");
  const sent = requests.find((r) => r.path === "/api/coach");
  expect(JSON.parse(sent.body).question).toBe(edited);
  fireEvent.click(await screen.findByRole("button", { name: "Stop audio" }));
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  await waitFor(() => expect(speechSynthesis.speak).toHaveBeenCalledTimes(2));
  fireEvent.click(screen.getByText("References consulted (1)"));
  expect(screen.getByRole("link", { name: /Workflow reference/ }).href).toBe("https://www.unicef.org/parenting/");
  fireEvent.change(screen.getByLabelText("Helpfulness rating"), { target: { value: "5" } });
  fireEvent.change(screen.getByLabelText("Optional comment"), { target: { value: "Clear steps." } });
  fireEvent.click(screen.getByRole("button", { name: "Save feedback" }));
  await screen.findByText(/your feedback was saved/);
  cleanup();
  await openWorkspace();
  fireEvent.click(await screen.findByRole("button", { name: edited }));
  await screen.findByText("Talk gently while dressing.");
  expect(screen.getByLabelText("Helpfulness rating").value).toBe("5");
  expect(screen.getByLabelText("Optional comment").value).toBe("Clear steps.");
  fireEvent.click(screen.getByRole("button", { name: `More options for ${edited}` }));
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: edited })).toBeNull());
  const response = await nativeFetch(`${base}/conversations?child_id=workflow-child`);
  expect(await response.json()).toEqual([]);
});

it("handles generation failure and cancellation without resending or losing a new draft", async () => {
  const input = await openWorkspace();
  fireEvent.change(input, { target: { value: "I need dressing ideas during an outage" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await screen.findByText("Something went wrong. Please try again.");
  fireEvent.change(input, { target: { value: "Slow dressing ideas" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await waitFor(() => expect(requests.filter((r) => r.path === "/api/coach")).toHaveLength(2));
  fireEvent.change(input, { target: { value: "Next draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Stop waiting" }));
  await screen.findByText(/Request cancelled\. Reopen/);
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 600)); });
  expect(input.value).toBe("Next draft");
  expect(screen.queryByText("Talk gently while dressing.")).toBeNull();
  expect(requests.filter((r) => r.path === "/api/coach")).toHaveLength(2);
});

it("keeps each child's conversations separate when switching profiles", async () => {
  const request = globalThis.fetch;
  let profileRequests = 0, releaseProfiles;
  const profilesReady = new Promise((resolve) => { releaseProfiles = resolve; });
  vi.stubGlobal("fetch", async (path, options) => {
    const response = await request(path, options);
    // The selector reloads profiles after the initial chat history has loaded.
    if (path === "/api/children" && ++profileRequests === 2) await profilesReady;
    return response;
  });
  const first = "How can I talk while dressing?";
  try {
    const input = await openWorkspace();
    fireEvent.change(input, { target: { value: first } });
    fireEvent.keyDown(input, { key: "Enter" });
    await screen.findByText("Talk gently while dressing.");
    expect(screen.queryByRole("button", { name: /Workflow child/ })).toBeNull();
  } finally {
    releaseProfiles();
  }
  fireEvent.click(await screen.findByRole("button", { name: /Workflow child/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Other child/ }));
  await screen.findByRole("textbox", { name: "Question" });
  expect(screen.queryByRole("button", { name: first })).toBeNull();
  expect(screen.queryByText("Talk gently while dressing.")).toBeNull();
  fireEvent.click(await screen.findByRole("button", { name: /Other child/ }));
  fireEvent.click(screen.getByRole("button", { name: /Workflow child/ }));
  fireEvent.click(await screen.findByRole("button", { name: first }));
  await screen.findByText("Talk gently while dressing.");
});
