import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import vm from "node:vm";
import { Blob as NodeBlob } from "node:buffer";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import GuidanceWorkspace from "../../frontend/src/components/GuidanceWorkspace";
import usePlaybackPreference from "../../frontend/src/hooks/usePlaybackPreference";
import useAccountAccess from "../../frontend/src/hooks/useAccountAccess";
import { auth } from "../../frontend/src/services/firebase";

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
  window.history.replaceState(null, "", "/");
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

it("renders a real checked stream before generation finishes and enables feedback after saving", async () => {
  const input = await openWorkspace();
  fireEvent.change(input, { target: { value: "How can I encourage babbling?" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await screen.findByText("Talk gently.");
  expect(screen.getByRole("button", { name: "Stop waiting" }).disabled).toBe(false);
  expect(screen.getByRole("button", { name: "Listen" }).disabled).toBe(true);
  expect(screen.queryByRole("combobox", { name: "Helpfulness rating" })).toBeNull();
  await nativeFetch(`${base}/__workflow/continue`, { method: "POST" });
  await screen.findByText("Talk gently. Pause and listen.");
  await waitFor(() => expect(screen.getByRole("button", { name: "Listen" }).disabled).toBe(false));
  expect(screen.getByRole("combobox", { name: "Helpfulness rating" })).toBeTruthy();
  expect(requests.filter(request => request.path === "/api/coach")).toHaveLength(1);
});

it("removes a partial reply when streaming is cancelled", async () => {
  const input = await openWorkspace();
  fireEvent.change(input, { target: { value: "How can I encourage babbling?" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await screen.findByText("Talk gently.");
  fireEvent.click(screen.getByRole("button", { name: "Stop waiting" }));
  await screen.findByText("Request cancelled.");
  expect(screen.queryByText("Talk gently.")).toBeNull();
  expect(screen.queryByRole("combobox", { name: "Helpfulness rating" })).toBeNull();
  await nativeFetch(`${base}/__workflow/continue`, { method: "POST" });
});

it("opens chat from one verified startup request without reloading consent or profiles", async () => {
  function StartupWorkspace() {
    const access = useAccountAccess(auth.currentUser);
    return access.verified ? <GuidanceWorkspace userId="workflow-account" startup={access.startup} /> : <p>Checking access</p>;
  }
  render(<StartupWorkspace />);
  await screen.findByRole("textbox", { name: "Question" });
  await waitFor(() => expect(screen.queryByText("Loading conversations…")).toBeNull());
  expect(requests.filter(r => r.path === "/api/me/startup")).toHaveLength(1);
  expect(requests.filter(r => ["/api/me", "/api/privacy/consent", "/api/children"].includes(r.path))).toHaveLength(0);
});

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
  expect(JSON.parse(sent.body).start_conversation).toBe(true);
  expect(requests.filter((r) => r.path === "/api/conversations" && r.method === "POST")).toHaveLength(0);
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
  fireEvent.click(await screen.findByRole("link", { name: edited }));
  await screen.findByText("Talk gently while dressing.");
  expect(screen.getByLabelText("Helpfulness rating").value).toBe("5");
  expect(screen.getByLabelText("Optional comment").value).toBe("Clear steps.");
  const options = screen.getByRole("button", { name: `More options for ${edited}` });
  await waitFor(() => expect(options.disabled).toBe(false));
  fireEvent.click(options);
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  await waitFor(() => expect(screen.queryByRole("link", { name: edited })).toBeNull());
  const response = await nativeFetch(`${base}/conversations?child_id=workflow-child`);
  expect(await response.json()).toEqual([]);
});

it("saves and reloads a checked language refusal through the streaming API", async () => {
  const question = "Mtoto wangu ana homa";
  const input = await openWorkspace();
  fireEvent.change(input, { target: { value: question } });
  fireEvent.keyDown(input, { key: "Enter" });
  await screen.findByRole("heading", { name: "Please use English" });
  await waitFor(() => expect(screen.queryByRole("button", { name: "Stop waiting" })).toBeNull());
  expect(screen.getByText(/Kwa sasa LittleCare/)).toBeTruthy();
  expect(screen.queryByText("Talk gently while dressing.")).toBeNull();
  cleanup();
  await openWorkspace();
  fireEvent.click(await screen.findByRole("link", { name: question }));
  await screen.findByRole("heading", { name: "Please use English" });
  expect(screen.getByText(/Kwa sasa LittleCare/)).toBeTruthy();
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
  const first = "How can I talk while dressing?";
  const input = await openWorkspace();
  fireEvent.change(input, { target: { value: first } });
  fireEvent.keyDown(input, { key: "Enter" });
  await screen.findByText("Talk gently while dressing.");
  expect(requests.filter((request) => request.path === "/api/children")).toHaveLength(1);
  fireEvent.change(input, { target: { value: "My next draft" } });
  fireEvent.click(await screen.findByRole("button", { name: /Workflow child/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Other child/ }));
  await screen.findByRole("textbox", { name: "Question" });
  expect(screen.queryByRole("link", { name: first })).toBeNull();
  expect(screen.getByText("Talk gently while dressing.").closest("[hidden]")).not.toBeNull();
  fireEvent.click(await screen.findByRole("button", { name: /Other child/ }));
  fireEvent.click(screen.getByRole("button", { name: /Workflow child/ }));
  await screen.findByText("Talk gently while dressing.");
  expect(screen.getByRole("textbox", { name: "Question" }).value).toBe("My next draft");
  expect(requests.filter((request) => request.path.startsWith("/api/conversations?")
    && new URL(request.path, base).searchParams.get("child_id") === "workflow-child")).toHaveLength(1);
});

it("opens chat from verified startup data without repeating consent and profile requests", async () => {
  const consent = await (await nativeFetch(`${base}/privacy/consent`)).json();
  const children = await (await nativeFetch(`${base}/children`)).json();
  render(<GuidanceWorkspace userId="workflow-account" startup={{ consent, children }} />);
  await screen.findByRole("textbox", { name: "Question" });
  expect(requests.filter((request) => ["/api/children", "/api/privacy/consent"].includes(request.path))).toHaveLength(0);
  expect(await screen.findByRole("button", { name: /Workflow child/ })).toBeTruthy();
});
