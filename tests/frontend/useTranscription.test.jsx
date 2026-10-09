import { StrictMode } from "react";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import useTranscription from "../../frontend/src/hooks/useTranscription";
import { transcribeAudio } from "../../frontend/src/services/transcription";

vi.mock("../../frontend/src/services/transcription", () => ({ transcribeAudio: vi.fn() }));
const makeRecording = () => ({ wavBlob: new Blob(["audio"], { type: "audio/wav" }) });
const response = (text) => ({ text, audio_seconds: 1, processing_seconds: 0.3 });
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

beforeEach(() => { transcribeAudio.mockReset(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

// a completed recording triggers one request, even with react development replay.
it("submits once in strict mode and allows editing without resubmitting", async () => {
  transcribeAudio.mockResolvedValue(response("hello"));
  const recording = makeRecording();
  const { result } = renderHook(() => useTranscription(recording), {
    wrapper: ({ children }) => <StrictMode>{children}</StrictMode>,
  });
  await waitFor(() => expect(result.current.status).toBe("success"));
  expect(transcribeAudio).toHaveBeenCalledTimes(1);
  act(() => result.current.setText("corrected words"));
  expect(result.current.text).toBe("corrected words");
  expect(transcribeAudio).toHaveBeenCalledTimes(1);
});

it("waits until there is a prepared recording", async () => {
  const { result } = renderHook(() => useTranscription(null));
  await act(async () => {});
  expect(result.current.status).toBe("idle");
  expect(transcribeAudio).not.toHaveBeenCalled();
});

it("cancels and ignores a late response, then supports explicit retry", async () => {
  const pending = deferred();
  transcribeAudio.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(response("retry result"));
  const recording = makeRecording();
  const { result } = renderHook(() => useTranscription(recording));
  await waitFor(() => expect(transcribeAudio).toHaveBeenCalledTimes(1));
  const signal = transcribeAudio.mock.calls[0][1];
  act(() => result.current.cancel());
  expect(signal.aborted).toBe(true);
  await act(async () => pending.resolve(response("old result")));
  expect(result.current.status).toBe("cancelled");
  expect(result.current.text).toBe("");
  act(() => { result.current.retry(); result.current.retry(); });
  await waitFor(() => expect(result.current.text).toBe("retry result"));
  expect(transcribeAudio).toHaveBeenCalledTimes(2);
});

it("does not replace a new transcript with an older response", async () => {
  const old = deferred();
  transcribeAudio.mockReturnValueOnce(old.promise).mockResolvedValueOnce(response("new"));
  const { result, rerender } = renderHook(({ recording }) => useTranscription(recording), {
    initialProps: { recording: makeRecording() },
  });
  await waitFor(() => expect(transcribeAudio).toHaveBeenCalledTimes(1));
  const oldSignal = transcribeAudio.mock.calls[0][1];
  rerender({ recording: makeRecording() });
  await waitFor(() => expect(result.current.text).toBe("new"));
  expect(oldSignal.aborted).toBe(true);
  await act(async () => old.resolve(response("old")));
  expect(result.current.text).toBe("new");
});

it("aborts when unmounted", async () => {
  transcribeAudio.mockReturnValue(new Promise(() => {}));
  const recording = makeRecording();
  const { unmount } = renderHook(() => useTranscription(recording));
  await waitFor(() => expect(transcribeAudio).toHaveBeenCalledTimes(1));
  const signal = transcribeAudio.mock.calls[0][1];
  unmount();
  expect(signal.aborted).toBe(true);
});

it("reports timeout and ignores a response arriving afterward", async () => {
  vi.useFakeTimers();
  const pending = deferred();
  transcribeAudio.mockReturnValue(pending.promise);
  const recording = makeRecording();
  const { result } = renderHook(() => useTranscription(recording));
  await act(async () => {});
  await act(async () => { vi.advanceTimersByTime(60000); });
  expect(result.current.status).toBe("error");
  expect(result.current.error).toContain("timed out");
  expect(transcribeAudio.mock.calls[0][1].aborted).toBe(true);
  await act(async () => pending.resolve(response("late")));
  expect(result.current.text).toBe("");
});

it("handles silence and request failures without automatic retry", async () => {
  transcribeAudio.mockResolvedValueOnce(response("")).mockRejectedValueOnce(new Error("server busy"));
  const { result, rerender } = renderHook(({ recording }) => useTranscription(recording), {
    initialProps: { recording: makeRecording() },
  });
  await waitFor(() => expect(result.current.status).toBe("success"));
  expect(result.current.text).toBe("");
  rerender({ recording: makeRecording() });
  await waitFor(() => expect(result.current.error).toBe("server busy"));
  expect(transcribeAudio).toHaveBeenCalledTimes(2);
});
