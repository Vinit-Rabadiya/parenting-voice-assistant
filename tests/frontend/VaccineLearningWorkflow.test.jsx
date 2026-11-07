import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import GuidanceWorkspace from "../../frontend/src/components/GuidanceWorkspace";
import { getConversation, listConversations, requestCoaching } from "../../frontend/src/services/caregiving";

const { consent } = vi.hoisted(() => ({ consent: { allowed: true } }));
vi.mock("../../frontend/src/services/caregiving", () => ({
  requestCoaching: vi.fn(), listConversations: vi.fn(), getConversation: vi.fn(), deleteConversation: vi.fn(), sendFeedback: vi.fn(),
}));
vi.mock("../../frontend/src/components/PrivacyConsent", () => ({ default: ({ children }) => children(consent.allowed, true) }));
vi.mock("../../frontend/src/components/ChildProfiles", () => ({
  default: ({ onSelect }) => <button onClick={() => onSelect({ id: "baby", name: "Baby", age_label: "6 months", in_scope: true })}>Select baby</button>,
}));
vi.mock("../../frontend/src/components/MicrophoneControls", () => ({ default: () => <button>Record into message</button> }));
const originalMethods = Object.fromEntries(["showModal", "close"].map(name =>
  [name, Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name)]));

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-07T12:00:00Z"));
  consent.allowed = true;
  window.history.replaceState(null, "", "/");
  listConversations.mockResolvedValue([]);
  requestCoaching.mockImplementation(async payload => ({ conversation_id: payload.conversation_id,
    message_id: "answer", answer: "Example saved vaccine explanation.", status: "vaccination_notice" }));
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value() { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value() { this.open = false; } });
  vi.stubGlobal("fetch", vi.fn(() => { throw new Error("Unexpected network call"); }));
});
afterEach(() => {
  cleanup(); vi.useRealTimers(); vi.unstubAllGlobals();
  for (const [name, descriptor] of Object.entries(originalMethods)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else delete HTMLDialogElement.prototype[name];
  }
});

async function selectBaby() {
  fireEvent.click(screen.getByRole("button", { name: "Select baby" }));
  await waitFor(() => expect(listConversations).toHaveBeenCalledTimes(1));
}
async function openEducation() {
  fireEvent.click(screen.getByRole("button", { name: "Understand vaccines" }));
  return screen.findByRole("dialog", { name: "Understand my baby's vaccines" });
}

it("opens and searches without fetching records, generating, saving, or mounting education on startup", async () => {
  render(<GuidanceWorkspace userId="parent" />);
  await selectBaby();
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.queryByText(/Vaccines help the immune system/)).toBeNull();
  await openEducation();
  expect(screen.queryByRole("button", { name: "Record into message" })).toBeNull();
  fireEvent.change(screen.getByLabelText("Find a vaccine name or question"), { target: { value: "tcv" } });
  expect(screen.getByRole("heading", { name: "TCV — typhoid" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Close vaccine explanations" }));
  expect(screen.getByRole("button", { name: "Record into message" })).toBeTruthy();
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Understand vaccines" }));
  expect(requestCoaching).not.toHaveBeenCalled();
  expect(listConversations).toHaveBeenCalledTimes(1);
  expect(fetch).not.toHaveBeenCalled();
});

it("preserves an unsent message rather than replacing it with a prepared question", async () => {
  render(<GuidanceWorkspace userId="parent" />);
  await selectBaby();
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "My own unsent question" } });
  await openEducation();
  expect(screen.getByRole("button", { name: "Open in new chat" }).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Close vaccine explanations" }));
  expect(screen.getByLabelText("Question").value).toBe("My own unsent question");
  expect(requestCoaching).not.toHaveBeenCalled();
});

it("prepares an editable question and uses the existing checked coaching path only on Send", async () => {
  render(<GuidanceWorkspace userId="parent" />);
  await selectBaby();
  await openEducation();
  fireEvent.click(screen.getByRole("button", { name: "PCV — pneumococcal" }));
  fireEvent.click(screen.getByRole("button", { name: "Open in new chat" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByLabelText("Question").value).toBe("What does PCV mean in my baby's vaccination booklet?");
  expect(requestCoaching).not.toHaveBeenCalled();
  await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText("Question")));
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await screen.findByText("Example saved vaccine explanation.");
  expect(requestCoaching).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
    child_id: "baby", question: "What does PCV mean in my baby's vaccination booklet?", support_country: "KE", start_conversation: true,
  }), expect.any(Object));
});

it("keeps education readable without allowing a follow-up before consent", async () => {
  consent.allowed = false;
  render(<GuidanceWorkspace userId="parent" />);
  await selectBaby();
  await openEducation();
  expect(screen.getByText(/Vaccines help the immune system/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Open in new chat" }).disabled).toBe(true);
  expect(requestCoaching).not.toHaveBeenCalled();
});

it("closes education and releases the dialog when the workspace becomes inactive", async () => {
  const view = render(<GuidanceWorkspace userId="parent" />);
  await selectBaby();
  await openEducation();
  view.rerender(<GuidanceWorkspace userId="parent" isActive={false} />);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.body.style.overflow).not.toBe("hidden");
  view.rerender(<GuidanceWorkspace userId="parent" />);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByRole("button", { name: "Record into message" })).toBeTruthy();
});

it.each(["explanation", "age visit"])("starts a separate conversation from an existing chat for a vaccine %s", async origin => {
  listConversations.mockResolvedValue([{ id: "previous-chat", title: "Previous conversation" }]);
  getConversation.mockResolvedValue({ id: "previous-chat", child_id: "baby", messages: [
    { id: "previous-answer", role: "assistant", text: "Earlier saved guidance.", status: "answered" },
  ] });
  render(<GuidanceWorkspace userId="parent" />);
  await selectBaby();
  fireEvent.click(await screen.findByRole("link", { name: "Previous conversation" }));
  await screen.findByText("Earlier saved guidance.");
  expect(window.location.pathname).toBe("/chat/previous-chat");
  await openEducation();
  let question;
  if (origin === "explanation") {
    fireEvent.click(screen.getByRole("button", { name: "PCV — pneumococcal" }));
    fireEvent.click(screen.getByRole("button", { name: "Open in new chat" }));
    question = "What does PCV mean in my baby's vaccination booklet?";
  } else {
    fireEvent.click(screen.getByRole("button", { name: "By age: days, weeks and months" }));
    fireEvent.click(screen.getByRole("button", { name: "Open 14-week visit in new chat" }));
    question = "Explain Kenya's routine vaccination visit at 14 weeks. What is each vaccine for?";
  }
  expect(window.location.pathname).toBe("/");
  expect(screen.queryByText("Earlier saved guidance.")).toBeNull();
  expect(screen.getByRole("link", { name: "Previous conversation" })).toBeTruthy();
  expect(screen.getByLabelText("Question").value).toBe(question);
  expect(requestCoaching).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await screen.findByText("Example saved vaccine explanation.");
  expect(requestCoaching.mock.calls[0][0]).toMatchObject({ question, start_conversation: true, child_id: "baby" });
  expect(requestCoaching.mock.calls[0][0].conversation_id).not.toBe("previous-chat");
  expect(getConversation).toHaveBeenCalledTimes(1);
});
