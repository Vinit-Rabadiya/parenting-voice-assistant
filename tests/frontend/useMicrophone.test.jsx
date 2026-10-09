import vm from "node:vm";
import { StrictMode } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import useMicrophone from "../../frontend/src/hooks/useMicrophone";
import { createWavBlob } from "../../frontend/src/utils/audio";
import workletCode from "../../frontend/public/audio/capture.worklet.js?raw";

vi.mock("../../frontend/src/utils/audio", () => ({ createWavBlob: vi.fn() }));

let contexts;
let nodes;
let getUserMedia;
let stream;
let track;

// hold an async result until a test deliberately resolves it.
function deferred() {
  let resolve;
  const promise = new Promise((yes) => { resolve = yes; });
  return { promise, resolve };
}

// provide controllable browser resources without opening a physical microphone.
beforeEach(() => {
  vi.useFakeTimers();
  contexts = [];
  nodes = [];
  track = { stop: vi.fn(), onended: null };
  stream = { getTracks: () => [track] };
  getUserMedia = vi.fn().mockResolvedValue(stream);
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  createWavBlob.mockReset();
  createWavBlob.mockResolvedValue(new Blob(["wav"], { type: "audio/wav" }));

  vi.stubGlobal("AudioContext", class {
    constructor() {
      this.sampleRate = 48000;
      this.state = "running";
      this.destination = {};
      this.resume = vi.fn().mockResolvedValue(undefined);
      this.close = vi.fn(async () => { this.state = "closed"; });
      this.audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) };
      this.source = { connect: vi.fn(), disconnect: vi.fn() };
      this.createMediaStreamSource = vi.fn(() => this.source);
      contexts.push(this);
    }
  });

  vi.stubGlobal("AudioWorkletNode", class {
    constructor(context, name) {
      expect(name).toBe("microphone-capture");
      this.context = context;
      this.connect = vi.fn();
      this.disconnect = vi.fn();
      this.onprocessorerror = null;
      this.pendingMessages = [];
      this.respondToStop = true;
      this.port = {
        onmessage: null,
        close: vi.fn(),
        postMessage: vi.fn((data) => {
          if (this.respondToStop) this.processor.port.onmessage({ data });
        }),
      };
      const node = this;
      let Processor;
      // run the actual worklet with a simulated message port.
      vm.runInNewContext(workletCode, {
        Float32Array,
        AudioWorkletProcessor: class {
          constructor() {
            this.port = { postMessage: (data) => {
              node.pendingMessages.push(Promise.resolve().then(() => node.port.onmessage?.({ data })));
            } };
          }
        },
        registerProcessor: (_, implementation) => { Processor = implementation; },
      });
      this.processor = new Processor();
      nodes.push(this);
    }

    // emulate audio-thread input and allow queued messages to reach the hook.
    async feed(...channels) {
      this.processor.process([channels]);
      await Promise.all(this.pendingMessages.splice(0));
    }
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

// verify cleanup by observable resource calls rather than hook implementation details.
function expectReleased(context = contexts[0], node = nodes[0], audioTrack = track) {
  expect(audioTrack.stop).toHaveBeenCalled();
  expect(context.close).toHaveBeenCalled();
  expect(context.source.disconnect).toHaveBeenCalled();
  expect(node.disconnect).toHaveBeenCalled();
  expect(node.port.close).toHaveBeenCalled();
  expect(node.port.onmessage).toBeNull();
  expect(vi.getTimerCount()).toBe(0);
}

// stop must flush a partial worklet buffer before preparing the complete recording.
it("preserves mono samples including the final partial batch on stop", async () => {
  const { result } = renderHook(() => useMicrophone(), {
    wrapper: ({ children }) => <StrictMode>{children}</StrictMode>,
  });
  await act(async () => { await result.current.start(); });
  expect(result.current.status).toBe("recording");
  expect(contexts[0].audioWorklet.addModule).toHaveBeenCalledWith("/audio/capture.worklet.js");
  expect(contexts[0].source.connect).toHaveBeenCalledWith(nodes[0]);
  expect(nodes[0].connect).toHaveBeenCalledWith(contexts[0].destination);

  await act(async () => {
    await nodes[0].feed(new Float32Array(2048).fill(0.5), new Float32Array(2048).fill(-0.25));
    await nodes[0].feed(new Float32Array(128).fill(0.75));
  });
  expect(createWavBlob).not.toHaveBeenCalled();
  await act(async () => {
    result.current.stop();
    result.current.stop();
    await Promise.all(nodes[0].pendingMessages.splice(0));
  });

  expect(nodes[0].port.postMessage).toHaveBeenCalledExactlyOnceWith({ type: "stop" });
  expect(createWavBlob).toHaveBeenCalledTimes(1);
  const recording = createWavBlob.mock.calls[0][0];
  expect(recording.sampleRate).toBe(48000);
  expect(recording.chunks.map((chunk) => chunk.length)).toEqual([2048, 128]);
  expect(recording.chunks[0].every((sample) => sample === 0.125)).toBe(true);
  expect(recording.chunks[1].every((sample) => sample === 0.75)).toBe(true);
  expect(result.current.recording.wavBlob.type).toBe("audio/wav");
  expect(result.current.status).toBe("idle");
  expectReleased();
});

// elapsed time must stop capture even when no complete worklet buffer arrived.
it("automatically stops at 30 seconds and flushes the remaining samples", async () => {
  const { result } = renderHook(() => useMicrophone());
  await act(async () => { await result.current.start(); });
  await act(async () => { await nodes[0].feed(new Float32Array(128).fill(0.1)); });
  await act(async () => { await vi.advanceTimersByTimeAsync(29999); });
  expect(result.current.status).toBe("recording");
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(result.current.status).toBe("idle");
  expect(createWavBlob.mock.calls[0][0].chunks[0].length).toBe(128);
  expectReleased();
});

// the sample limit protects duration independently of browser timer scheduling.
it("trims samples at 30 seconds using the actual context rate", async () => {
  const { result } = renderHook(() => useMicrophone());
  await act(async () => { await result.current.start(); });
  await act(async () => { await nodes[0].feed(new Float32Array(48000 * 30 + 4096)); });
  const recording = createWavBlob.mock.calls[0][0];
  expect(recording.chunks.reduce((sum, chunk) => sum + chunk.length, 0)).toBe(48000 * 30);
  expect(result.current.status).toBe("idle");
  expectReleased();
});

// navigation must discard unfinished audio and release every active resource.
it("releases capture resources on unmount without preparing audio", async () => {
  const { result, unmount } = renderHook(() => useMicrophone());
  await act(async () => { await result.current.start(); });
  await act(async () => { await nodes[0].feed(new Float32Array(2048)); });
  unmount();
  expect(createWavBlob).not.toHaveBeenCalled();
  expectReleased();
});

// a delayed permission result cannot reopen capture after stop or unmount.
it.each(["stop", "unmount"])("discards late microphone permission after %s", async (action) => {
  const permission = deferred();
  getUserMedia.mockReturnValue(permission.promise);
  const { result, unmount } = renderHook(() => useMicrophone());
  let starting;
  await act(async () => { starting = result.current.start(); });
  expect(getUserMedia).toHaveBeenCalledTimes(1);
  await act(async () => { await result.current.start(); });
  expect(contexts).toHaveLength(1);
  if (action === "stop") act(() => result.current.stop());
  else unmount();
  await act(async () => { permission.resolve(stream); await starting; });
  expect(track.stop).toHaveBeenCalled();
  expect(contexts[0].close).toHaveBeenCalled();
  expect(nodes).toHaveLength(0);
  expect(createWavBlob).not.toHaveBeenCalled();
  expect(vi.getTimerCount()).toBe(0);
});

// cancelling conversion must not let its result replace a newer recording session.
it("ignores old preparation results after cancellation and restart", async () => {
  const conversion = deferred();
  createWavBlob.mockReturnValueOnce(conversion.promise);
  const { result } = renderHook(() => useMicrophone());
  await act(async () => { await result.current.start(); });
  await act(async () => { await nodes[0].feed(new Float32Array(128)); });
  await act(async () => { result.current.stop(); });
  expect(result.current.status).toBe("preparing");
  expectReleased();
  act(() => result.current.stop());
  await act(async () => { await result.current.start(); });
  expect(result.current.status).toBe("recording");
  await act(async () => { conversion.resolve(new Blob(["old wav"])); });
  expect(result.current.recording).toBeNull();
  expect(result.current.status).toBe("recording");
  expect(contexts[1].close).not.toHaveBeenCalled();
});

// a missing acknowledgement must release the microphone rather than hang forever.
it("times out when the worklet cannot acknowledge stop", async () => {
  const { result } = renderHook(() => useMicrophone());
  await act(async () => { await result.current.start(); });
  nodes[0].respondToStop = false;
  act(() => result.current.stop());
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(result.current.status).toBe("idle");
  expect(result.current.error).toContain("could not finish");
  expect(result.current.recording).toBeNull();
  expectReleased();
});

// device or processor failure must stop capture and report an error.
it.each(["processor", "device"])("cleans up after a %s failure", async (failure) => {
  const { result } = renderHook(() => useMicrophone());
  await act(async () => { await result.current.start(); });
  act(() => {
    if (failure === "processor") nodes[0].onprocessorerror();
    else track.onended();
  });
  expect(result.current.status).toBe("idle");
  expect(result.current.error).not.toBe("");
  expect(result.current.recording).toBeNull();
  expectReleased();
});

// failed wav preparation must not publish a recording and should permit another attempt.
it("recovers from preparation failure", async () => {
  createWavBlob.mockRejectedValueOnce(new Error("resampling failed"));
  const { result } = renderHook(() => useMicrophone());
  await act(async () => { await result.current.start(); });
  await act(async () => { await nodes[0].feed(new Float32Array(128)); });
  await act(async () => { result.current.stop(); });
  expect(result.current.error).toContain("Could not prepare");
  expect(result.current.recording).toBeNull();
  expectReleased();
  await act(async () => { await result.current.start(); });
  expect(result.current.status).toBe("recording");
  expect(result.current.error).toBe("");
});

// permission denial must close the context and explain how to restore access.
it("handles denied permission without leaving an audio context open", async () => {
  getUserMedia.mockRejectedValueOnce(new DOMException("blocked", "NotAllowedError"));
  const { result } = renderHook(() => useMicrophone());
  await act(async () => { await result.current.start(); });
  expect(result.current.status).toBe("idle");
  expect(result.current.error).toContain("Microphone to Allow");
  expect(contexts[0].close).toHaveBeenCalled();
  expect(nodes).toHaveLength(0);
  expect(vi.getTimerCount()).toBe(0);
});
