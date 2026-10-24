import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import GuidanceAnswer from "../../frontend/src/components/GuidanceAnswer";
import { sendFeedback } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({ sendFeedback: vi.fn() }));
const message = { id: "answer-1", text: "Talk softly.", status: "answered", citations: [], processing_seconds: 1 };
beforeEach(() => {
  vi.resetAllMocks(); sendFeedback.mockResolvedValue({});
  vi.stubGlobal("speechSynthesis", { speak: vi.fn(), cancel: vi.fn() });
  vi.stubGlobal("SpeechSynthesisUtterance", function(text) { this.text = text; });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("keeps the answer readable when browser audio is unavailable", () => {
  vi.stubGlobal("speechSynthesis", undefined);
  render(<GuidanceAnswer message={message} />);
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  expect(screen.getByText(/Audio playback is unavailable/)).toBeTruthy();
  expect(screen.getByText(message.text)).toBeTruthy();
});

it("shows playback errors and lets Listen retry without losing text", () => {
  render(<GuidanceAnswer message={message} />);
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  const utterance = window.speechSynthesis.speak.mock.calls[0][0];
  expect(utterance.text).toBe(message.text);
  act(() => utterance.onerror({ error: "network" }));
  expect(screen.getByText(/Audio could not be played/)).toBeTruthy();
  expect(screen.getByText(message.text)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  expect(screen.queryByText(/Audio could not be played/)).toBeNull();
  expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(2);
});

it("handles synchronous audio failures", () => {
  window.speechSynthesis.speak.mockImplementation(() => { throw new Error("Unavailable"); });
  render(<GuidanceAnswer message={message} />);
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  expect(screen.getByText(/Audio could not be played/)).toBeTruthy();
  expect(screen.getByText(message.text)).toBeTruthy();
});

it("detaches playback callbacks when stopped or removed", () => {
  const { unmount } = render(<GuidanceAnswer message={message} />);
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  const first = window.speechSynthesis.speak.mock.calls[0][0];
  fireEvent.click(screen.getByRole("button", { name: "Stop audio" }));
  expect(first.onerror).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  const second = window.speechSynthesis.speak.mock.calls[1][0];
  unmount();
  expect(second.onerror).toBeNull();
});

it("saves a numeric rating and reasons without inventing a boolean value", async () => {
  render(<GuidanceAnswer message={message} childName="Baby" conversationId="chat-1" />);
  fireEvent.change(screen.getByLabelText("Helpfulness rating"), { target: { value: "2" } });
  fireEvent.click(screen.getByText("Add an optional reason"));
  fireEvent.click(screen.getByLabelText("Repeated advice"));
  fireEvent.click(screen.getByRole("button", { name: "Save rating" }));
  await waitFor(() => expect(sendFeedback).toHaveBeenCalledWith("answer-1", {
    rating: 2, reasons: ["repeated_advice"], comment: null, conversation_id: "chat-1",
  }));
  expect(sendFeedback.mock.calls[0][1]).not.toHaveProperty("helpful");
  await screen.findByText(/your feedback was saved/);
});

it("keeps historical boolean feedback without choosing a numeric equivalent", () => {
  render(<GuidanceAnswer message={{ ...message, feedback: { helpful: true } }} conversationId="chat-1" />);
  expect(screen.getByLabelText("Helpfulness rating").value).toBe("");
  expect(screen.getByRole("button", { name: "Save rating" }).disabled).toBe(true);
});

it("lets a caregiver edit a saved numeric rating through the existing feedback path", async () => {
  render(<GuidanceAnswer message={{ ...message, feedback: { rating: 2, reasons: ["unclear"] } }} conversationId="chat-1" />);
  expect(screen.getByLabelText("Helpfulness rating").value).toBe("2");
  fireEvent.change(screen.getByLabelText("Helpfulness rating"), { target: { value: "5" } });
  fireEvent.click(screen.getByRole("button", { name: "Save rating" }));
  await waitFor(() => expect(sendFeedback).toHaveBeenCalledWith("answer-1", {
    rating: 5, reasons: ["unclear"], comment: null, conversation_id: "chat-1",
  }));
  await screen.findByText(/your feedback was saved/);
});

it("shows an error and allows retry when feedback fails", async () => {
  sendFeedback.mockRejectedValueOnce(new Error("Please retry."));
  render(<GuidanceAnswer message={message} conversationId="chat-1" />);
  fireEvent.change(screen.getByLabelText("Helpfulness rating"), { target: { value: "5" } });
  fireEvent.click(screen.getByRole("button", { name: "Save rating" }));
  await screen.findByText("Please retry.");
  expect(screen.getByRole("button", { name: "Save rating" }).disabled).toBe(false);
});

it.each([
  ["clarification", "Tell me a little more"], ["unrelated", "Baby-care topics only"],
  ["professional_referral", "Professional advice needed"], ["insufficient_references", "More information needed"],
])("labels the %s outcome without claiming guidance was generated", (kind, heading) => {
  render(<GuidanceAnswer message={{ ...message, status: "no_evidence", response_kind: kind }} />);
  expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
  expect(screen.getByText(/No coaching answer was generated/)).toBeTruthy();
});
