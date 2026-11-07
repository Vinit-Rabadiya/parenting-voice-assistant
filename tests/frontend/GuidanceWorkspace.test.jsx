import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import GuidanceWorkspace from "../../frontend/src/components/GuidanceWorkspace";
import { createConversation, deleteConversation, getConversation, listConversations, requestCoaching } from "../../frontend/src/services/caregiving";
const { consentState } = vi.hoisted(() => ({ consentState: { allowed: true } }));

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

// Workspace behaviour is tested with prior consent; PrivacyConsent has its own tests.
vi.mock("../../frontend/src/components/PrivacyConsent", () => ({ default: ({ children }) => children(consentState.allowed) }));

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  vi.resetAllMocks();
  consentState.allowed = true;
  listConversations.mockResolvedValue([]);
  createConversation.mockResolvedValue({ id: "chat-1", title: "New conversation" });
  vi.stubGlobal("SpeechSynthesisUtterance", function (text) { this.text = text; });
  vi.stubGlobal("speechSynthesis", { cancel: vi.fn(), speak: vi.fn() });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function selectProfile() {
  fireEvent.click(screen.getByRole("button", { name: "Select test profile" }));
  await screen.findByRole("button", { name: "New chat" });
}

it("replaces a limited provider preview without mixing it into the backup answer", async () => {
  let emit, finish, identifier;
  requestCoaching.mockImplementation((payload, { onEvent }) => new Promise(resolve => {
    emit = onEvent; finish = resolve; identifier = payload.conversation_id;
  }));
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Babbling ideas?" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await waitFor(() => expect(typeof emit).toBe("function"));
  act(() => emit({ type: "delta", text: "Old provider preview." }));
  await screen.findByText("Old provider preview.");
  act(() => emit({ type: "reset" }));
  expect(screen.queryByText("Old provider preview.")).toBeNull();
  act(() => emit({ type: "delta", text: "Backup answer." }));
  await screen.findByText("Backup answer.");
  await act(async () => finish({ conversation_id: identifier, message_id: "backup-answer",
    answer: "Backup answer.", status: "answered" }));
  expect(screen.queryByText("Old provider preview.")).toBeNull();
  expect(screen.getAllByText("Backup answer.")).toHaveLength(1);
  expect(requestCoaching).toHaveBeenCalledTimes(1);
});

it("sends a first turn in one request while history is still loading", async () => {
  let finishHistory;
  listConversations.mockReturnValue(new Promise(resolve => { finishHistory = resolve; }));
  requestCoaching.mockImplementation(async payload => ({ conversation_id: payload.conversation_id,
    message_id: "first-answer", answer: "Talk softly.", status: "answered" }));
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Feeding ideas" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await screen.findByText("Talk softly.");
  const payload = requestCoaching.mock.calls[0][0];
  expect(payload.start_conversation).toBe(true);
  expect(payload.conversation_id).toMatch(/^[0-9a-f-]{36}$/);
  expect(createConversation).not.toHaveBeenCalled();
  await act(async () => finishHistory([{ id: payload.conversation_id, title: "Old snapshot title" }, { id: "older", title: "Earlier chat" }]));
  expect(screen.getAllByRole("link", { name: "Feeding ideas" })).toHaveLength(1);
  expect(screen.getByRole("link", { name: "Earlier chat" })).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Another idea" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await waitFor(() => expect(requestCoaching).toHaveBeenCalledTimes(2));
  expect(requestCoaching.mock.calls[1][0].start_conversation).toBeUndefined();
});

it.each([404, 200])("checks an unconfirmed first conversation before the next send (lookup %s)", async status => {
  requestCoaching.mockRejectedValueOnce(Object.assign(new Error("Request limit reached"), { status: 429 }))
    .mockImplementationOnce(async payload => ({ conversation_id: payload.conversation_id,
      message_id: "answer", answer: "Talk softly.", status: "answered" }));
  getConversation.mockImplementation(async () => {
    if (status === 404) throw Object.assign(new Error("Conversation not found"), { status: 404 });
    return { messages: [] };
  });
  render(<GuidanceWorkspace />);
  await selectProfile();
  const send = text => {
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: text } });
    fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  };
  send("Feeding ideas");
  await screen.findByText("Request limit reached");
  send("More feeding ideas");
  await screen.findByText("Talk softly.");
  expect(getConversation).toHaveBeenCalledTimes(1);
  const first = requestCoaching.mock.calls[0][0], second = requestCoaching.mock.calls[1][0];
  expect(first.conversation_id).toBe(second.conversation_id);
  expect(second.start_conversation).toBe(status === 404 ? true : undefined);
});

it("does not restore a deleted conversation when the initial history response arrives late", async () => {
  let finishHistory;
  listConversations.mockReturnValue(new Promise(resolve => { finishHistory = resolve; }));
  requestCoaching.mockImplementation(async payload => ({ conversation_id: payload.conversation_id,
    message_id: "first-answer", answer: "Talk softly.", status: "answered" }));
  vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Feeding ideas" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await screen.findByText("Talk softly.");
  fireEvent.click(screen.getByRole("button", { name: "More options for Feeding ideas" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  await waitFor(() => expect(screen.queryByRole("link", { name: "Feeding ideas" })).toBeNull());
  const id = requestCoaching.mock.calls[0][0].conversation_id;
  await act(async () => finishHistory([{ id, title: "Feeding ideas" }]));
  expect(screen.queryByRole("link", { name: "Feeding ideas" })).toBeNull();
});

it("uses Kenya by default without country or support-contact controls", async () => {
  requestCoaching.mockResolvedValue({ status: "vaccination_notice", answer: "At 9 months: MR 1, IPV 2 and TCV. Confirm the next appointment with the clinic.",
    vaccination_country: "KE", citations: [
      { passage_id: "vaccination-kenya-schedule", source_title: "WHO: Kenya vaccination schedule", source_url: "https://immunizationdata.who.int/global/wiise-detail-page/vaccination-schedule-for-country_name?ISO_3_CODE=KEN", pdf_page: null, title: "Kenya vaccination information" },
      { passage_id: "vaccination-kenya-updates", source_title: "WHO Kenya Annual Report 2025", source_url: "https://www.afro.who.int/sites/default/files/2026-04/WHO%20Kenya%20Annual%20Report%202025.pdf", pdf_page: 11, title: "Kenya vaccination information" },
    ], processing_seconds: 0.1, interaction_id: null });
  render(<GuidanceWorkspace />);
  await selectProfile();
  expect(screen.queryByLabelText("Country")).toBeNull();
  expect(screen.queryByText("Other countries (not available yet)")).toBeNull();
  expect(screen.queryByLabelText("Show Kenya support contacts")).toBeNull();
  expect(screen.queryByLabelText("Vaccination country (optional)")).toBeNull();
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Which vaccines are due?" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await screen.findByRole("heading", { name: "Vaccination information" });
  expect(requestCoaching.mock.calls.at(-1)[0]).not.toHaveProperty("vaccination_country");
  expect(requestCoaching.mock.calls.at(-1)[0].support_country).toBe("KE");
  expect(screen.getByText("Vaccination country: Kenya")).toBeTruthy();
  expect(screen.getByText("At 9 months: MR 1, IPV 2 and TCV. Confirm the next appointment with the clinic.")).toBeTruthy();
  fireEvent.click(screen.getByText("References consulted (2)"));
  expect(screen.getByRole("link", { name: /WHO: Kenya vaccination schedule/ }).href).toContain("ISO_3_CODE=KEN");
  expect(screen.getByRole("link", { name: /WHO Kenya Annual Report 2025, page 11/ }).href).toContain("2025.pdf");
});

it("allows history review and deletion without mounting input or feedback before consent", async () => {
  consentState.allowed = false;
  listConversations.mockResolvedValue([{ id: "saved-chat", title: "Feeding conversation" }]);
  getConversation.mockResolvedValue({ messages: [{ id: "answer-1", role: "assistant", text: "Talk softly.",
    status: "answered", citations: [], feedback: null }] });
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.click(screen.getByRole("link", { name: "Feeding conversation" }));
  await screen.findByText("Talk softly.");
  expect(screen.queryByRole("textbox", { name: "Question" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Record into message" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Save feedback" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "More options for Feeding conversation" }));
  expect(screen.getByRole("button", { name: "Delete conversation" })).toBeTruthy();
  expect(requestCoaching).not.toHaveBeenCalled();
});

it("sends a message with Enter through the existing submission flow", async () => {
  requestCoaching.mockResolvedValue({ conversation_id: "chat-1", message_id: "answer-1",
    answer: "Talk softly.", status: "answered", citations: [], processing_seconds: 1 });
  render(<GuidanceWorkspace />);
  await selectProfile();
  const input = screen.getByLabelText("Question");
  fireEvent.change(input, { target: { value: "Feeding ideas" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await screen.findByText("Talk softly.");
  expect(requestCoaching).toHaveBeenCalledTimes(1);
  expect(requestCoaching.mock.calls[0][0].question).toBe("Feeding ideas");
  expect(input.value).toBe("");
  expect(createConversation).not.toHaveBeenCalled();
  expect(requestCoaching.mock.calls[0][0].start_conversation).toBe(true);
  expect(requestCoaching.mock.calls[0][0].conversation_id).toMatch(/^[0-9a-f-]{36}$/);
});

it("allows sending while history is pending and preserves the new chat when history arrives", async () => {
  let finishHistory;
  listConversations.mockReturnValue(new Promise((resolve) => { finishHistory = resolve; }));
  requestCoaching.mockResolvedValue({ message_id: "answer-1", answer: "Try a soft rattle.",
    status: "answered", citations: [], processing_seconds: 1 });
  render(<GuidanceWorkspace />);
  await selectProfile();
  expect(screen.getByText("Loading conversations…")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Playing ideas" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await screen.findByText("Try a soft rattle.");
  await act(async () => { finishHistory([{ id: "older", title: "Older conversation" }]); });
  expect(screen.getByRole("link", { name: "Playing ideas" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Older conversation" })).toBeTruthy();
});

it("can start the same new conversation after a failed request that never created it", async () => {
  requestCoaching.mockRejectedValueOnce(Object.assign(new Error("Please wait before trying again."), { status: 429 }))
    .mockResolvedValueOnce({ message_id: "answer-1", answer: "Try a soft rattle.",
      status: "answered", citations: [], processing_seconds: 1 });
  getConversation.mockRejectedValueOnce(Object.assign(new Error("Not found"), { status: 404 }));
  render(<GuidanceWorkspace />);
  await selectProfile();
  const input = screen.getByLabelText("Question");
  fireEvent.change(input, { target: { value: "Playing ideas" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await screen.findByText("Please wait before trying again.");
  expect(screen.queryByRole("button", { name: "New conversation" })).toBeNull();
  const first = requestCoaching.mock.calls[0][0];
  fireEvent.change(input, { target: { value: "Another play question" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await screen.findByText("Try a soft rattle.");
  expect(requestCoaching.mock.calls[1][0]).toMatchObject({ conversation_id: first.conversation_id, start_conversation: true });
  expect(createConversation).not.toHaveBeenCalled();
});

it("preserves the open conversation and draft when leaving and returning to chat", async () => {
  listConversations.mockResolvedValue([{ id: "saved-chat", title: "Feeding conversation" }]);
  getConversation.mockResolvedValue({ messages: [
    { id: "a1", role: "assistant", text: "Talk softly.", status: "answered", citations: [] },
  ] });
  const view = render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.click(screen.getByRole("link", { name: "Feeding conversation" }));
  await screen.findByText("Talk softly.");
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "My next question" } });
  view.rerender(<GuidanceWorkspace isActive={false} />);
  expect(screen.queryByRole("button", { name: "Record into message" })).toBeNull();
  view.rerender(<GuidanceWorkspace isActive />);
  expect(screen.getByLabelText("Question").value).toBe("My next question");
  expect(screen.getByText("Talk softly.")).toBeTruthy();
  expect(listConversations).toHaveBeenCalledTimes(1);
  expect(getConversation).toHaveBeenCalledTimes(1);
});

it.each([
  ["Shift+Enter", { shiftKey: true }],
  ["composition", { isComposing: true }],
  ["composition key code", { keyCode: 229 }],
  ["held Enter", { repeat: true }],
])("does not submit on %s", async (_name, modifiers) => {
  render(<GuidanceWorkspace />);
  await selectProfile();
  const input = screen.getByLabelText("Question");
  fireEvent.change(input, { target: { value: "Feeding ideas" } });
  fireEvent.keyDown(input, { key: "Enter", ...modifiers });
  expect(createConversation).not.toHaveBeenCalled();
  expect(requestCoaching).not.toHaveBeenCalled();
});

it("does not submit blank messages or send again while preparing guidance", async () => {
  requestCoaching.mockReturnValue(new Promise(() => {}));
  render(<GuidanceWorkspace />);
  await selectProfile();
  const input = screen.getByLabelText("Question");
  fireEvent.keyDown(input, { key: "Enter" });
  expect(createConversation).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: "Feeding ideas" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await waitFor(() => expect(requestCoaching).toHaveBeenCalledTimes(1));
  fireEvent.keyDown(input, { key: "Enter" });
  expect(requestCoaching).toHaveBeenCalledTimes(1);
});

it("moves the message into the thread immediately and replaces Send with Stop", async () => {
  let finish;
  requestCoaching.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  render(<GuidanceWorkspace />);
  await selectProfile();
  const input = screen.getByLabelText("Question");
  fireEvent.change(input, { target: { value: "Feeding ideas" } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(input.value).toBe("");
  expect(screen.getByText("Feeding ideas").closest(".caregiver-message")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Stop waiting" }).querySelector("rect")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Get guidance" })).toBeNull();
  expect(screen.getAllByText("One moment…")).toHaveLength(1);
  expect(screen.queryByText("Waiting for guidance…")).toBeNull();
  await waitFor(() => expect(requestCoaching).toHaveBeenCalledTimes(1));
  fireEvent.change(input, { target: { value: "My next draft" } });
  finish({ answer: "Talk softly.", status: "answered", citations: [], message_id: "a1" });
  await screen.findByText("Talk softly.");
  const thread = screen.getByRole("region", { name: "Test child" });
  expect(within(thread).getAllByText("Feeding ideas")).toHaveLength(1);
  expect(input.value).toBe("My next draft");
  expect(screen.getByRole("button", { name: "Get guidance" })).toBeTruthy();
});

it.each([390, 1280])("scrolls the chat to the new answer once at viewport width %s", async (width) => {
  vi.stubGlobal("innerWidth", width);
  const scroll = vi.fn();
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  HTMLElement.prototype.scrollTo = scroll;
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function () {
    return { top: this.classList.contains("guidance-answer") ? 450 : 100 };
  });
  let finish;
  requestCoaching.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Feeding ideas" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await waitFor(() => expect(requestCoaching).toHaveBeenCalledTimes(1));
  scroll.mockClear();
  await act(async () => finish({ answer: "Talk softly.", status: "answered", message_id: "new-answer" }));
  await screen.findByText("Talk softly.");
  expect(scroll).toHaveBeenCalledTimes(1);
  expect(scroll.mock.calls[0][0]).toEqual({ top: 338, behavior: "smooth" });
  await waitFor(() => expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1));
  act(() => window.speechSynthesis.speak.mock.calls[0][0].onstart());
  fireEvent.click(screen.getByRole("button", { name: "Stop audio" }));
  expect(scroll).toHaveBeenCalledTimes(1);
  delete HTMLElement.prototype.scrollTo;
});

it("ignores a late response after cancellation even if the request ignores its abort signal", async () => {
  let finish;
  requestCoaching.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Feeding ideas" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await waitFor(() => expect(requestCoaching).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Stop waiting" }));
  await act(async () => finish({ answer: "This answer arrived too late.", status: "answered", message_id: "late-answer" }));
  expect(screen.queryByText("This answer arrived too late.")).toBeNull();
  expect(window.speechSynthesis.speak).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Get guidance" })).toBeTruthy();
});

it("keeps the submitted message in the thread after stopping guidance", async () => {
  requestCoaching.mockImplementation((_payload, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(new Error("Stopped waiting for guidance.")), { once: true });
  }));
  render(<GuidanceWorkspace />);
  await selectProfile();
  const input = screen.getByLabelText("Question");
  fireEvent.change(input, { target: { value: "Feeding ideas" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await waitFor(() => expect(requestCoaching).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Stop waiting" }));
  expect(screen.getByText("Request cancelled.")).toBeTruthy();
  await screen.findByText("Request cancelled. Reopen this conversation to check for a reply before sending again.");
  expect(input.value).toBe("");
  expect(screen.getByText("Feeding ideas")).toBeTruthy();
  expect(screen.queryByText(/Answer not confirmed/)).toBeNull();
  expect(requestCoaching).toHaveBeenCalledTimes(1);
});

it("shows saved sources in a collapsed disclosure and includes a privacy notice", async () => {
  listConversations.mockResolvedValue([{ id: "saved-chat", title: "Feeding conversation" }]);
  getConversation.mockResolvedValue({ messages: [{ id: "answer-1", role: "assistant", text: "Talk softly.",
    status: "answered", citations: [{ passage_id: "p1", source_title: "Reference", title: "Feeding",
      pdf_page: 7, source_url: "https://example.test/reference" }] }] });
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.click(screen.getByRole("link", { name: "Feeding conversation" }));
  const summary = await screen.findByText("References consulted (1)");
  expect(summary.closest("details").open).toBe(false);
  fireEvent.click(summary);
  expect(summary.closest("details").open).toBe(true);
  expect(screen.getByRole("link", { name: "Reference, page 7: Feeding" })).toBeTruthy();
  expect(screen.getByText("Conversation privacy")).toBeTruthy();
});

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
  await waitFor(() => expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1));
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
  expect(screen.getByText("Response time: 0.20 seconds.")).toBeTruthy();
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
  fireEvent.click(screen.getByRole("link", { name: "Feeding conversation" }));
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
  expect(screen.queryByRole("button", { name: "Save feedback" })).toBeNull();
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
  fireEvent.click(screen.getByRole("link", { name: "Feeding advice" }));
  await screen.findByText("Talk softly.");
  expect(screen.queryByRole("button", { name: "Delete conversation" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "More options for Play advice" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  await waitFor(() => expect(screen.queryByRole("link", { name: "Play advice" })).toBeNull());
  expect(deleteConversation).toHaveBeenCalledWith("other-chat");
  expect(screen.getByText("Talk softly.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Feeding advice" }).getAttribute("aria-current")).toBe("page");
});

it("keeps a conversation when deletion is cancelled", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  listConversations.mockResolvedValue([{ id: "chat-1", title: "Feeding advice" }]);
  render(<GuidanceWorkspace />);
  await selectProfile();
  fireEvent.click(screen.getByRole("button", { name: "More options for Feeding advice" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  expect(deleteConversation).not.toHaveBeenCalled();
  expect(screen.getByRole("link", { name: "Feeding advice" })).toBeTruthy();
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
  expect(screen.getByRole("link", { name: "Feeding advice" })).toBeTruthy();
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
  fireEvent.click(screen.getByRole("link", { name: "Feeding advice" }));
  await screen.findByText("Talk softly.");
  expect(window.location.pathname).toBe("/chat/chat-1");
  fireEvent.click(screen.getByRole("button", { name: "More options for Feeding advice" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  await waitFor(() => expect(screen.queryByText("Talk softly.")).toBeNull());
  expect(window.location.pathname).toBe("/");
  expect(screen.getByRole("heading", { name: "What are you doing with your baby today?" })).toBeTruthy();
});
