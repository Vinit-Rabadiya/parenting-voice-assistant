import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import MicrophoneControls from "../../frontend/src/components/MicrophoneControls";
import { transcribeAudio } from "../../frontend/src/services/transcription";

const { microphone } = vi.hoisted(() => ({ microphone: {
  status: "idle", error: "", recording: null, start: vi.fn(), stop: vi.fn(),
} }));
vi.mock("../../frontend/src/hooks/useMicrophone", () => ({ default: () => microphone }));
vi.mock("../../frontend/src/services/transcription", () => ({ transcribeAudio: vi.fn() }));

beforeEach(() => {
  microphone.status = "idle";
  microphone.error = "";
  microphone.recording = null;
  transcribeAudio.mockReset();
});
afterEach(() => { cleanup(); });

// the actual component and request hook connect a completed wav to editable text.
it("automatically submits after stop and displays editable transcript", async () => {
  transcribeAudio.mockResolvedValue({ text: "My baby is hungry.", audio_seconds: 1, processing_seconds: 0.2 });
  const { rerender } = render(<MicrophoneControls />);
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  expect(microphone.start).toHaveBeenCalledOnce();
  expect(transcribeAudio).not.toHaveBeenCalled();

  microphone.status = "recording";
  rerender(<MicrophoneControls />);
  fireEvent.click(screen.getByRole("button", { name: "Stop and transcribe" }));
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
