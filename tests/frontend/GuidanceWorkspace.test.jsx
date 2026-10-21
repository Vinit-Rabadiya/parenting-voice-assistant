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

it("shows an escalation without claiming it is generated coaching", async () => {
  requestCoaching.mockResolvedValue({
    status: "escalated", safety: "escalate", answer: "Seek urgent medical care now.",
    citations: [{ passage_id: "safety-who-etat", source_title: "WHO emergency guidance",
      pdf_page: null, source_url: "https://www.who.int", title: "Overview" }],
    processing_seconds: 0.2, interaction_id: "test-interaction",
  });
  render(<GuidanceWorkspace />);
  fireEvent.click(screen.getByRole("button", { name: "Select test profile" }));
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "My baby is choking." } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  expect(await screen.findByRole("heading", { name: "Seek urgent medical care" })).toBeTruthy();
  expect(screen.getByText(/Coaching was skipped/)).toBeTruthy();
  expect(screen.queryByText(/page null/)).toBeNull();
  expect(screen.queryByText(/using age-aware reference material/)).toBeNull();
});

it("does not offer feedback when an escalation could not be saved", async () => {
  requestCoaching.mockResolvedValue({
    status: "escalated", safety: "escalate", answer: "Seek urgent medical care now.",
    citations: [], processing_seconds: 0.2, interaction_id: null,
  });
  render(<GuidanceWorkspace />);
  fireEvent.click(screen.getByRole("button", { name: "Select test profile" }));
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "My baby is choking." } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  expect(await screen.findByRole("heading", { name: "Seek urgent medical care" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Helpful" })).toBeNull();
  expect(screen.getByRole("button", { name: "Listen" })).toBeTruthy();
});

it("shows location-labelled support contacts only from the returned resources", async () => {
  requestCoaching.mockResolvedValue({
    status: "crisis_support", safety: "escalate", answer: "Please seek immediate support.",
    citations: [], processing_seconds: 0.2, interaction_id: null,
    support_resources: [{ service: "Example verified service", label: "Service website",
      url: "https://example.test/support", availability: "Example service hours",
      source_url: "https://example.test/about", verified_on: "2026-10-20", country: "KE" }],
  });
  render(<GuidanceWorkspace />);
  fireEvent.click(screen.getByRole("button", { name: "Select test profile" }));
  fireEvent.change(screen.getByLabelText("Support resources location (optional)"), { target: { value: "KE" } });
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "I need immediate support." } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  expect(await screen.findByRole("heading", { name: "Immediate support" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Kenya support contacts" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Service website" }).getAttribute("href")).toBe("https://example.test/support");
  expect(requestCoaching.mock.calls.at(-1)[0].support_country).toBe("KE");
  expect(screen.queryByText(/using age-aware reference material/)).toBeNull();
});
