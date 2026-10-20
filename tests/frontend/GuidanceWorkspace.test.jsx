import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import GuidanceWorkspace from "../../frontend/src/components/GuidanceWorkspace";
import { requestCoaching } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({
  requestCoaching: vi.fn(), sendFeedback: vi.fn(),
}));
vi.mock("../../frontend/src/components/MicrophoneControls", () => ({ default: () => null }));
vi.mock("../../frontend/src/components/ChildProfiles", () => ({
  default: ({ onSelect }) => <button onClick={() => onSelect({
    id: "test-child", name: "Test child", age_label: "6 months", in_scope: true,
  })}>Select test profile</button>,
}));

beforeEach(() => {
  vi.stubGlobal("SpeechSynthesisUtterance", function (text) { this.text = text; });
  vi.stubGlobal("speechSynthesis", { cancel: vi.fn(), speak: vi.fn() });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("shows a blocked outcome distinctly and reads only the returned replacement", async () => {
  const replacement = "For medical advice, contact a qualified health professional.";
  requestCoaching.mockResolvedValue({
    status: "safety_blocked", answer: replacement, citations: [],
    processing_seconds: 1.2, interaction_id: "test-interaction",
  });
  render(<GuidanceWorkspace />);
  fireEvent.click(screen.getByRole("button", { name: "Select test profile" }));
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Feeding ideas" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  expect(await screen.findByRole("heading", { name: "Guidance could not be provided" })).toBeTruthy();
  expect(screen.getByText(replacement)).toBeTruthy();
  expect(screen.queryByText("Sources used")).toBeNull();
  expect(screen.queryByText(/No coaching answer was generated/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  expect(window.speechSynthesis.speak.mock.calls[0][0].text).toBe(replacement);
});
