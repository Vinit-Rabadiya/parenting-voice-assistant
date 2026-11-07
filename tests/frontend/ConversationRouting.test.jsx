import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import GuidanceWorkspace from "../../frontend/src/components/GuidanceWorkspace";
import { publishChildProfiles } from "../../frontend/src/services/childSelection";
import { getConversation, listConversations, requestCoaching } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({
  getConversation: vi.fn(), listConversations: vi.fn(), requestCoaching: vi.fn(),
  sendFeedback: vi.fn(), deleteConversation: vi.fn(),
}));
vi.mock("../../frontend/src/components/PrivacyConsent", () => ({ default: ({ children }) => children(true, true) }));
vi.mock("../../frontend/src/components/MicrophoneControls", () => ({ default: () => null }));
vi.mock("../../frontend/src/components/ChildProfiles", () => ({
  default: ({ initialChildren, onSelect }) => <>{initialChildren.map(child =>
    <button key={child.id} onClick={() => onSelect(child)}>Select {child.name}</button>)}</>,
}));
const children = [
  { id: "one", name: "First child", age_label: "6 months", in_scope: true },
  { id: "two", name: "Second child", age_label: "18 months", in_scope: true },
];
const snapshot = (id, child_id = "two") => ({ id, child_id, messages: [
  { id: `${id}-message`, role: "user", text: `Saved message ${id}` },
] });
const show = () => render(<GuidanceWorkspace userId="account" startup={{ children }} />);
const visit = path => act(() => {
  window.history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
});

it("applies saved account profile edits without losing the chat draft or reloading history", async () => {
  window.history.replaceState(null, "", "/chat/saved-chat");
  show();
  await screen.findByText("Saved message saved-chat");
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Unsent question" } });
  act(() => publishChildProfiles("different-account", [{ ...children[1], name: "Wrong account" }]));
  expect(screen.queryByRole("heading", { name: "Wrong account" })).toBeNull();
  act(() => publishChildProfiles("account", [children[0], { ...children[1], name: "Updated name" }]));
  await screen.findByRole("heading", { name: "Updated name" });
  expect(screen.getByLabelText("Question").value).toBe("Unsent question");
  expect(screen.getByText("Saved message saved-chat")).toBeTruthy();
  expect(window.location.pathname).toBe("/chat/saved-chat");
  expect(getConversation).toHaveBeenCalledTimes(1);
  expect(listConversations).toHaveBeenCalledTimes(1);
});
beforeEach(() => {
  vi.resetAllMocks();
  window.history.replaceState(null, "", "/");
  listConversations.mockResolvedValue([]);
  getConversation.mockImplementation(async id => snapshot(id));
});
afterEach(cleanup);

it("exposes a native chat link and leaves its right-click menu available", async () => {
  listConversations.mockResolvedValue([{ id: "saved-chat", title: "Feeding conversation" }]);
  show();
  fireEvent.click(screen.getByRole("button", { name: "Select First child" }));
  const link = await screen.findByRole("link", { name: "Feeding conversation" });
  expect(link.getAttribute("href")).toBe("/chat/saved-chat");
  expect(new URL(link.href).origin).toBe(window.location.origin);
  expect(fireEvent.contextMenu(link)).toBe(true);
  expect(getConversation).not.toHaveBeenCalled();
  expect(requestCoaching).not.toHaveBeenCalled();
  expect(window.location.pathname).toBe("/");
});

it("opens an ordinary link click in place with one history read", async () => {
  listConversations.mockResolvedValue([{ id: "saved-chat", title: "Feeding conversation" }]);
  getConversation.mockResolvedValue(snapshot("saved-chat", "one"));
  show();
  fireEvent.click(screen.getByRole("button", { name: "Select First child" }));
  const link = await screen.findByRole("link", { name: "Feeding conversation" });
  expect(fireEvent.click(link)).toBe(false);
  await screen.findByText("Saved message saved-chat");
  expect(window.location.pathname).toBe("/chat/saved-chat");
  expect(link.getAttribute("aria-current")).toBe("page");
  expect(getConversation).toHaveBeenCalledTimes(1);
  expect(requestCoaching).not.toHaveBeenCalled();
});

it.each([
  ["click", { ctrlKey: true }], ["click", { metaKey: true }],
  ["click", { shiftKey: true }], ["click", { altKey: true }],
  ["auxclick", { button: 1 }],
])("leaves %s %j to the browser without changing the current chat", async (type, modifiers) => {
  listConversations.mockResolvedValue([{ id: "saved-chat", title: "Feeding conversation" }]);
  const view = show();
  fireEvent.click(screen.getByRole("button", { name: "Select First child" }));
  const link = await screen.findByRole("link", { name: "Feeding conversation" });
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Keep this draft" } });
  let browserHandlesLink;
  // Inspect after React's delegated handler, then suppress jsdom's unsupported navigation.
  view.container.addEventListener(type, event => {
    browserHandlesLink = !event.defaultPrevented;
    event.preventDefault();
  }, { once: true });
  fireEvent(link, new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, ...modifiers }));
  expect(browserHandlesLink).toBe(true);
  expect(getConversation).not.toHaveBeenCalled();
  expect(requestCoaching).not.toHaveBeenCalled();
  expect(window.location.pathname).toBe("/");
  expect(screen.getByLabelText("Question").value).toBe("Keep this draft");
});

it("blocks same-tab history navigation while an answer is in progress", async () => {
  let finish;
  listConversations.mockResolvedValue([{ id: "saved-chat", title: "Feeding conversation" }]);
  requestCoaching.mockImplementation(payload => new Promise(resolve => {
    finish = () => resolve({ conversation_id: payload.conversation_id, message_id: "new-answer",
      answer: "New answer.", status: "answered" });
  }));
  show();
  fireEvent.click(screen.getByRole("button", { name: "Select First child" }));
  const link = await screen.findByRole("link", { name: "Feeding conversation" });
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Feeding question" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await waitFor(() => expect(typeof finish).toBe("function"));
  expect(link.getAttribute("aria-disabled")).toBe("true");
  expect(fireEvent.click(link)).toBe(false);
  expect(getConversation).not.toHaveBeenCalled();
  await act(async () => finish());
  await screen.findByText("New answer.");
  expect(link.hasAttribute("aria-disabled")).toBe(false);
});

it("opens a bookmarked conversation under its owned child with one history read", async () => {
  window.history.replaceState(null, "", "/chat/saved-chat");
  show();
  await screen.findByText("Saved message saved-chat");
  expect(screen.getByRole("heading", { name: "Second child" })).toBeTruthy();
  expect(getConversation).toHaveBeenCalledTimes(1);
  expect(listConversations.mock.calls[0][0]).toBe("two");
  expect(requestCoaching).not.toHaveBeenCalled();
});

it("sets a successful new chat URL without reading it again", async () => {
  requestCoaching.mockImplementation(async payload => ({ conversation_id: payload.conversation_id,
    message_id: "answer", answer: "A new reply", status: "answered" }));
  show();
  fireEvent.click(screen.getByRole("button", { name: "Select First child" }));
  fireEvent.change(await screen.findByLabelText("Question"), { target: { value: "A new feeding question" } });
  fireEvent.click(screen.getByRole("button", { name: "Get guidance" }));
  await screen.findByText("A new reply");
  expect(window.location.pathname).toBe(`/chat/${requestCoaching.mock.calls[0][0].conversation_id}`);
  expect(getConversation).not.toHaveBeenCalled();
});

it("restores browser navigation and reuses a cached child conversation", async () => {
  window.history.replaceState(null, "", "/chat/second-chat");
  show();
  await screen.findByText("Saved message second-chat");
  fireEvent.click(screen.getByRole("button", { name: "Select First child" }));
  expect(window.location.pathname).toBe("/");
  visit("/chat/second-chat");
  await screen.findByRole("heading", { name: "Second child" });
  expect(getConversation).toHaveBeenCalledTimes(1);
});

it.each(["unknown-child", "different-id", "missing"])("rejects inaccessible history (%s)", async mode => {
  window.history.replaceState(null, "", "/chat/private-chat");
  if (mode === "missing") getConversation.mockRejectedValue(Object.assign(new Error("Not found"), { status: 404 }));
  else getConversation.mockResolvedValue(snapshot(mode === "different-id" ? "other-chat" : "private-chat",
    mode === "unknown-child" ? "unowned" : "two"));
  show();
  await screen.findByText("This conversation is unavailable for this account.");
  expect(screen.queryByText(/Saved message/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  await screen.findByLabelText("Question");
  expect(window.location.pathname).toBe("/");
});

it("ignores a late history response after navigating to another conversation", async () => {
  let finish;
  getConversation.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
    .mockResolvedValueOnce(snapshot("new-chat"));
  window.history.replaceState(null, "", "/chat/old-chat");
  show();
  await waitFor(() => expect(getConversation).toHaveBeenCalledTimes(1));
  visit("/chat/new-chat");
  await screen.findByText("Saved message new-chat");
  await act(async () => finish(snapshot("old-chat")));
  expect(screen.queryByText("Saved message old-chat")).toBeNull();
  expect(window.location.pathname).toBe("/chat/new-chat");
});

it("supports actual browser Back and Forward", async () => {
  window.history.replaceState(null, "", "/chat/bookmarked");
  show();
  await screen.findByText("Saved message bookmarked");
  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  expect(window.location.pathname).toBe("/");
  act(() => window.history.back());
  await screen.findByText("Saved message bookmarked");
  expect(window.location.pathname).toBe("/chat/bookmarked");
  act(() => window.history.forward());
  await waitFor(() => expect(window.location.pathname).toBe("/"));
  await waitFor(() => expect(screen.queryByText("Saved message bookmarked")).toBeNull());
});

it("does not show an aborted lookup error after returning to a new chat", async () => {
  let reject;
  getConversation.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
  window.history.replaceState(null, "", "/chat/pending");
  show();
  await waitFor(() => expect(getConversation).toHaveBeenCalledTimes(1));
  visit("/");
  await screen.findByLabelText("Question");
  await act(async () => reject(new DOMException("Aborted", "AbortError")));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByLabelText("Question")).toBeTruthy();
});
