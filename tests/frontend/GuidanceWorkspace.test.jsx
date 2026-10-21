import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import GuidanceWorkspace from "../../frontend/src/components/GuidanceWorkspace";
import { createConversation, deleteConversation, getConversation, listConversations, requestCoaching } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({
  requestCoaching: vi.fn(), sendFeedback: vi.fn(),
  createConversation: vi.fn(), getConversation: vi.fn(), listConversations: vi.fn(), deleteConversation: vi.fn(),
}));
vi.mock("../../frontend/src/components/MicrophoneControls", () => ({
  default: ({ onTranscriptChange, compact }) => <button type="button" onClick={() => onTranscriptChange("I am feeding my baby.")}>
    {compact ? "Record into message" : "Record transcript"}
  </button>,
}));
vi.mock("../../frontend/src/components/ChildProfiles", () => ({
  default: ({ onSelect }) => <button onClick={() => onSelect({
    id: "test-child", name: "Test child", age_label: "6 months", in_scope: true,
  })}>Select test profile</button>,
}));

beforeEach(() => {
  vi.resetAllMocks();
  listConversations.mockResolvedValue([]);
  createConversation.mockResolvedValue({ id: "chat-1", title: "New conversation" });
  vi.stubGlobal("SpeechSynthesisUtterance", function (text) { this.text = text; });
  vi.stubGlobal("speechSynthesis", { cancel: vi.fn(), speak: vi.fn() });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function selectProfile() {
  fireEvent.click(screen.getByRole("button", { name: "Select test profile" }));
  await waitFor(() => expect(screen.queryByText("Loading conversations…")).toBeNull());
}

it("shows a blocked outcome distinctly and reads only the returned replacement", async () => {
  const replacement = "For medical advice, contact a qualified health professional.";
  requestCoaching.mockResolvedValue({
    status: "safety_blocked", answer: replacement, citations: [],
    processing_seconds: 1.2, interaction_id: "test-interaction",
  });
  render(<GuidanceWorkspace />);
  await selectProfile();
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
  await selectProfile();
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "My baby is choking." } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  expect(await screen.findByRole("heading", { name: "Seek urgent medical care" })).toBeTruthy();
  expect(screen.getByText(/Coaching was skipped/)).toBeTruthy();
  expect(screen.queryByText(/page null/)).toBeNull();
  expect(screen.queryByText(/using age-aware reference material/)).toBeNull();
});

it("shares one editable message box between typing and recording", async () => {
  render(<GuidanceWorkspace />);
  await selectProfile();
  expect(screen.getAllByRole("textbox")).toHaveLength(1);
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Typed draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Record into message" }));
  expect(screen.getByLabelText("Question").value).toBe("I am feeding my baby.");
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "I am feeding my six-month-old baby." } });
  expect(screen.getByLabelText("Question").value).toBe("I am feeding my six-month-old baby.");
});

it("changes from the welcome layout to the conversation layout after an answer", async () => {
  requestCoaching.mockResolvedValue({ conversation_id: "chat-1", message_id: "answer-1",
    interaction_id: null, answer: "Talk softly.", status: "answered", citations: [], processing_seconds: 1 });
  const { container } = render(<GuidanceWorkspace />);
  await selectProfile();
  expect(screen.getByRole("heading", { name: "What are you doing with your baby today?" })).toBeTruthy();
  expect(container.querySelector(".chat-main--empty")).not.toBeNull();
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Feeding ideas" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await screen.findByText("Talk softly.");
  expect(container.querySelector(".chat-main--empty")).toBeNull();
  expect(screen.getByRole("region", { name: "Message composer" })).toBeTruthy();
});

it("opens a saved conversation without another generation call", async () => {
  listConversations.mockResolvedValue([{ id: "saved-chat", title: "Feeding conversation" }]);
  getConversation.mockResolvedValue({ messages: [
    { id: "question-1", role: "user", text: "Feeding ideas" },
    { id: "answer-1", role: "assistant", text: "Talk softly.", status: "answered", citations: [], processing_seconds: 1 },
  ] });
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.click(screen.getByRole("button", { name: "Feeding conversation" }));
  await screen.findByText("Talk softly.");
  expect(screen.getByText("Feeding ideas")).toBeTruthy();
  expect(requestCoaching).not.toHaveBeenCalled();
});

it("does not offer feedback when an escalation could not be saved", async () => {
  requestCoaching.mockResolvedValue({
    status: "escalated", safety: "escalate", answer: "Seek urgent medical care now.",
    citations: [], processing_seconds: 0.2, interaction_id: null,
  });
  render(<GuidanceWorkspace />);
  await selectProfile();
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
  await selectProfile();
  fireEvent.change(screen.getByLabelText("Support resources location (optional)"), { target: { value: "KE" } });
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "I need immediate support." } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  expect(await screen.findByRole("heading", { name: "Immediate support" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Kenya support contacts" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Service website" }).getAttribute("href")).toBe("https://example.test/support");
  expect(requestCoaching.mock.calls.at(-1)[0].support_country).toBe("KE");
  expect(screen.queryByText(/using age-aware reference material/)).toBeNull();
});

it("deletes another conversation from its title menu without clearing the open chat", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  listConversations.mockResolvedValue([
    { id: "open-chat", title: "Feeding advice" }, { id: "other-chat", title: "Play advice" },
  ]);
  getConversation.mockResolvedValue({ messages: [
    { id: "answer-1", role: "assistant", text: "Talk softly.", citations: [], status: "answered" },
  ] });
  deleteConversation.mockResolvedValue(undefined);
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.click(screen.getByRole("button", { name: "Feeding advice" }));
  await screen.findByText("Talk softly.");
  expect(screen.queryByRole("button", { name: "Delete conversation" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "More options for Play advice" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Play advice" })).toBeNull());
  expect(deleteConversation).toHaveBeenCalledWith("other-chat");
  expect(screen.getByText("Talk softly.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Feeding advice" }).getAttribute("aria-pressed")).toBe("true");
});

it("keeps a conversation when deletion is cancelled", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  listConversations.mockResolvedValue([{ id: "chat-1", title: "Feeding advice" }]);
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.click(screen.getByRole("button", { name: "More options for Feeding advice" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  expect(deleteConversation).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Feeding advice" })).toBeTruthy();
});

it("closes conversation options with Escape and restores focus", async () => {
  listConversations.mockResolvedValue([{ id: "chat-1", title: "Feeding advice" }]);
  render(<GuidanceWorkspace />);
  await selectProfile();
  const trigger = screen.getByRole("button", { name: "More options for Feeding advice" });
  fireEvent.click(trigger);
  expect(screen.getByRole("button", { name: "Delete conversation" }).closest(".conversation-row")).toBeNull();
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Delete conversation" }));
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("button", { name: "Delete conversation" })).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

it("keeps the conversation visible when deletion fails", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  listConversations.mockResolvedValue([{ id: "chat-1", title: "Feeding advice" }]);
  deleteConversation.mockRejectedValue(new Error("Conversation deletion could not finish. Please retry."));
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.click(screen.getByRole("button", { name: "More options for Feeding advice" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  await screen.findByText("Conversation deletion could not finish. Please retry.");
  expect(screen.getByRole("button", { name: "Feeding advice" })).toBeTruthy();
});

it("returns to a new chat when the open conversation is deleted", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  listConversations.mockResolvedValue([{ id: "chat-1", title: "Feeding advice" }]);
  getConversation.mockResolvedValue({ messages: [
    { id: "answer-1", role: "assistant", text: "Talk softly.", citations: [], status: "answered" },
  ] });
  deleteConversation.mockResolvedValue(undefined);
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.click(screen.getByRole("button", { name: "Feeding advice" }));
  await screen.findByText("Talk softly.");
  fireEvent.click(screen.getByRole("button", { name: "More options for Feeding advice" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  await waitFor(() => expect(screen.queryByText("Talk softly.")).toBeNull());
  expect(screen.getByRole("heading", { name: "What are you doing with your baby today?" })).toBeTruthy();
});
