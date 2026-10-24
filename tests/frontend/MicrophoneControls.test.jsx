import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import MicrophoneControls from "../../frontend/src/components/MicrophoneControls";
import { transcribeAudio } from "../../frontend/src/services/transcription";

const { microphone } = vi.hoisted(() => ({ microphone: {
  status: "idle", error: "", recording: null, start: vi.fn(), stop: vi.fn(),
  pause: vi.fn(), resume: vi.fn(), cancel: vi.fn(),
} }));
vi.mock("../../frontend/src/hooks/useMicrophone", () => ({ default: () => microphone }));
vi.mock("../../frontend/src/services/transcription", () => ({ transcribeAudio: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
  microphone.status = "idle";
  microphone.error = "";
  microphone.recording = null;
  transcribeAudio.mockReset();
});
afterEach(() => { cleanup(); });

it("offers pause, resume, and discard controls without submitting audio", () => {
  microphone.status = "recording";
  const view = render(<MicrophoneControls compact />);
  fireEvent.click(screen.getByRole("button", { name: "Pause recording" }));
  expect(microphone.pause).toHaveBeenCalled();
  microphone.status = "paused";
  view.rerender(<MicrophoneControls compact />);
  fireEvent.click(screen.getByRole("button", { name: "Resume recording" }));
  expect(microphone.resume).toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Cancel recording" }));
  expect(microphone.cancel).toHaveBeenCalled();
  microphone.status = "idle";
  view.rerender(<MicrophoneControls compact />);
  expect(screen.getByText("Recording cancelled. Audio discarded.")).toBeTruthy();
  expect(transcribeAudio).not.toHaveBeenCalled();
});

it("clears the capture-busy state when controls leave the active chat", () => {
  microphone.status = "recording";
  const onCaptureStateChange = vi.fn();
  const view = render(<MicrophoneControls compact onCaptureStateChange={onCaptureStateChange} />);
  expect(onCaptureStateChange).toHaveBeenLastCalledWith(true);
  view.unmount();
  expect(onCaptureStateChange).toHaveBeenLastCalledWith(false);
});

it("passes compact-mode transcription to the message field without a second textarea", async () => {
  const onTranscriptChange = vi.fn();
  transcribeAudio.mockResolvedValue({ text: "I am feeding my baby.", audio_seconds: 1, processing_seconds: 0.2 });
  microphone.recording = { wavBlob: new Blob(["wav"]), chunks: [], sampleRate: 16000 };
  render(<MicrophoneControls compact onTranscriptChange={onTranscriptChange} />);
  await waitFor(() => expect(onTranscriptChange).toHaveBeenCalledWith("I am feeding my baby."));
  expect(screen.queryByRole("textbox")).toBeNull();
});

// the actual component and request hook connect a completed wav to editable text.
it("automatically submits after stop and displays editable transcript", async () => {
  transcribeAudio.mockResolvedValue({ text: "My baby is hungry.", audio_seconds: 1, processing_seconds: 0.2 });
  const { rerender } = render(<MicrophoneControls />);
  const microphoneButton = screen.getByRole("button", { name: "Start recording" });
  expect(microphoneButton.querySelector("svg")).not.toBeNull();
  expect(screen.queryByRole("button", { name: "Stop and transcribe" })).toBeNull();
  fireEvent.click(microphoneButton);
  expect(microphone.start).toHaveBeenCalledOnce();
  expect(transcribeAudio).not.toHaveBeenCalled();

  microphone.status = "recording";
  rerender(<MicrophoneControls />);
  expect(screen.getByRole("button", { name: "Stop and transcribe" })).toBe(microphoneButton);
  expect(microphoneButton.classList.contains("microphone-button--recording")).toBe(true);
  fireEvent.click(microphoneButton);
  expect(microphone.stop).toHaveBeenCalledOnce();

  microphone.status = "idle";
  microphone.recording = {
    wavBlob: new Blob(["wav"]), chunks: [new Float32Array(16000)], sampleRate: 16000,
  };
  rerender(<MicrophoneControls />);
  await waitFor(() => expect(screen.getByLabelText("Your transcript").value).toBe("My baby is hungry."));
  fireEvent.change(screen.getByLabelText("Your transcript"), { target: { value: "My baby is sleepy." } });
  expect(screen.getByLabelText("Your transcript").value).toBe("My baby is sleepy.");
  expect(transcribeAudio).toHaveBeenCalledOnce();
});

// the primary control cannot start new work while setup or conversion is pending.
it.each([
  ["requesting", "Waiting for microphone…"],
  ["preparing", "Preparing audio…"],
  ["stopping", "Stopping recording…"],
])("disables the microphone during %s with appropriate cancellation", (status, label) => {
  microphone.status = status;
  render(<MicrophoneControls />);
  const button = screen.getByRole("button", { name: label });
  expect(button.disabled).toBe(true);
  fireEvent.click(button);
  expect(microphone.start).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Cancel recording" }));
  expect(microphone.cancel).toHaveBeenCalledOnce();
  expect(microphone.stop).not.toHaveBeenCalled();
  expect(transcribeAudio).not.toHaveBeenCalled();
});

// a pending request shows a disabled microphone and a separate cancellation action.
it("prevents duplicate starts during transcription and restores the mic after cancel", async () => {
  transcribeAudio.mockReturnValueOnce(new Promise(() => {}));
  microphone.recording = { wavBlob: new Blob(["wav"]), chunks: [], sampleRate: 16000 };
  render(<MicrophoneControls />);
  await act(async () => {});
  const button = screen.getByRole("button", { name: "Transcribing…" });
  expect(button.disabled).toBe(true);
  fireEvent.click(button);
  expect(microphone.start).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Cancel transcription" }));
  expect(screen.getByRole("button", { name: "Start recording" }).disabled).toBe(false);
});

it("shows empty speech feedback and does not invent text", async () => {
  transcribeAudio.mockResolvedValue({ text: "", audio_seconds: 1, processing_seconds: 0.1 });
  microphone.recording = { wavBlob: new Blob(["wav"]), chunks: [], sampleRate: 16000 };
  render(<MicrophoneControls />);
  await waitFor(() => expect(screen.getByRole("status").textContent).toContain("No words"));
  expect(screen.getByLabelText("Your transcript").value).toBe("");
});

it("offers retry after failure and cancels a pending request", async () => {
  transcribeAudio.mockRejectedValueOnce(new Error("Speech service is busy."));
  microphone.recording = { wavBlob: new Blob(["wav"]), chunks: [], sampleRate: 16000 };
  render(<MicrophoneControls />);
  await screen.findByRole("alert");
  expect(screen.getByRole("alert").textContent).toBe("Speech service is busy.");
  transcribeAudio.mockReturnValueOnce(new Promise(() => {}));
  fireEvent.click(screen.getByRole("button", { name: "Retry transcription" }));
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "Cancel transcription" }));
  expect(transcribeAudio.mock.calls[1][1].aborted).toBe(true);
  expect(screen.getByRole("status").textContent).toContain("cancelled");
});
