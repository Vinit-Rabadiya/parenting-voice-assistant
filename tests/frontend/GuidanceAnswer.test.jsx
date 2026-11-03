import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import GuidanceAnswer from "../../frontend/src/components/GuidanceAnswer";
import { sendFeedback } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({ sendFeedback: vi.fn() }));
const message = { id: "answer-1", text: "Talk softly.", status: "answered", citations: [], processing_seconds: 1 };

it("shows guidance and preparation time without information-type labels", () => {
  render(<GuidanceAnswer message={{ ...message, text: "**General information:** Talk softly.", answer_basis: "general_information", reference_status: "unavailable" }} />);
  expect(screen.getByText("Talk softly.")).toBeTruthy();
  expect(screen.getByText("Response time: 1.00 seconds.")).toBeTruthy();
  expect(screen.queryByText(/General information|not verified against|Reference search is temporarily unavailable/)).toBeNull();
  expect(screen.queryByText(/References consulted/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  expect(window.speechSynthesis.speak.mock.calls[0][0].text).toBe("Talk softly.");
});
beforeEach(() => {
  vi.resetAllMocks(); sendFeedback.mockResolvedValue({});
  vi.stubGlobal("speechSynthesis", { speak: vi.fn(), cancel: vi.fn() });
  vi.stubGlobal("SpeechSynthesisUtterance", function(text) { this.text = text; });
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

it("shows emergency phone links on an urgent medical response", () => {
  render(<GuidanceAnswer message={{ ...message, status: "escalated",
    text: "Seek urgent medical care now.", support_resources: ["999", "112"].map((number) => ({
      label: number, url: `tel:${number}`, service: `Kenya emergency services (${number})`,
      country: "KE", availability: "For emergencies.", source_url: "https://disastermanagement.go.ke/",
      verified_on: "2026-10-29",
    })),
  }} />);
  expect(screen.getByRole("heading", { name: "Seek urgent medical care" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "999" }).getAttribute("href")).toBe("tel:999");
  expect(screen.getByRole("link", { name: "112" }).getAttribute("href")).toBe("tel:112");
});

it("lists hospitals by town separately from emergency and ambulance contacts", () => {
  render(<GuidanceAnswer message={{ ...message, status: "escalated", support_resources: [
    { label: "999", url: "tel:999", service: "Kenya emergency services", category: "emergency" },
    { label: "0721 225 285", url: "tel:+254721225285", service: "St John Ambulance Kenya", category: "ambulance" },
    { label: "020 272 6300", url: "tel:+254202726300", service: "Kenyatta National Hospital", category: "hospital", location: "Nairobi" },
  ] }} />);
  expect(screen.getByRole("link", { name: "999" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "0721 225 285" })).toBeTruthy();
  const summary = screen.getByText("Hospital contacts in Kenya (1)");
  expect(summary.closest("details").open).toBe(false);
  fireEvent.click(summary);
  expect(screen.getByRole("link", { name: "020 272 6300" }).getAttribute("href")).toBe("tel:+254202726300");
  expect(screen.getByText(/Kenyatta National Hospital — Nairobi/)).toBeTruthy();
});

it("reads formatted guidance without speaking markers or changing the displayed answer", () => {
  const text = "### Feeding\n* **Talk** gently.\n- Wait 5-10 seconds; do not force a response.\n1. Keep reading for 1.5 minutes.\nSee [a guide](https://example.test/guide).\n***\n_Listen_ and `respond`.";
  const saved = Object.freeze({ ...message, text });
  const view = render(<GuidanceAnswer message={saved} />);
  expect(screen.getByRole("heading", { name: "Feeding" })).toBeTruthy();
  expect(view.container.querySelector("strong").textContent).toBe("Talk");
  expect(screen.getByRole("link", { name: "a guide" }).href).toBe("https://example.test/guide");
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  expect(window.speechSynthesis.speak.mock.calls[0][0].text).toBe(
    "Feeding\nTalk gently.\nWait 5-10 seconds; do not force a response.\nKeep reading for 1.5 minutes.\nSee a guide.\n\nListen and respond.",
  );
  expect(saved.text).toBe(text);
});

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

it("shows the complete reply immediately and speaks once across rerenders", async () => {
  vi.useFakeTimers();
  const view = render(<StrictMode><GuidanceAnswer message={message} fresh /></StrictMode>);
  const text = view.container.querySelector(".guidance-text");
  expect(text.getAttribute("aria-busy")).toBe("false");
  expect(text.textContent).toBe(message.text);
  expect(window.speechSynthesis.speak).not.toHaveBeenCalled();
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(text.getAttribute("aria-busy")).toBe("false");
  expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1);
  expect(window.speechSynthesis.speak.mock.calls[0][0].text).toBe(message.text);
  view.rerender(<StrictMode><GuidanceAnswer message={{ ...message }} fresh /></StrictMode>);
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1);
  expect(screen.getAllByRole("button", { name: /Listen|Stop audio/ })).toHaveLength(1);
});

it("allows stopping during preparation and does not automatically restart", async () => {
  vi.useFakeTimers();
  render(<GuidanceAnswer message={message} fresh />);
  await act(async () => { await vi.advanceTimersByTimeAsync(1800); });
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(screen.getByText("Loading audio…")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Stop audio" }));
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Listen" })).toBeTruthy();
  expect(screen.queryByText("Loading audio…")).toBeNull();
});

it("shows long replies immediately and clears playback resources when removed", async () => {
  vi.useFakeTimers();
  const text = Array.from({ length: 40 }, () => "Talk gently and watch your baby's cues.").join("\n\n");
  const view = render(<GuidanceAnswer message={{ ...message, text }} fresh />);
  expect(view.container.querySelector(".guidance-text").textContent).toBe(text.replaceAll("\n", ""));
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(view.container.querySelector(".guidance-word--pending")).toBeNull();
  expect(window.speechSynthesis.speak.mock.calls[0][0].text).toBe(text);
  view.unmount();
  const second = render(<GuidanceAnswer message={{ ...message, id: "another-answer", text }} fresh />);
  second.unmount();
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});

it("returns to Listen when speech ends and supports manual replay", () => {
  render(<GuidanceAnswer message={message} />);
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  const speech = window.speechSynthesis.speak.mock.calls[0][0];
  act(() => speech.onstart());
  expect(screen.getByRole("button", { name: "Stop audio" })).toBeTruthy();
  act(() => speech.onend());
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(2);
});

it("handles an utterance mute or interruption without claiming to know device volume", () => {
  render(<GuidanceAnswer message={message} />);
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  const speech = window.speechSynthesis.speak.mock.calls[0][0];
  speech.volume = 0;
  act(() => speech.onstart());
  expect(screen.getByText(/Audio is muted/)).toBeTruthy();
  expect(screen.getByText("Can't hear the guidance? Check your device volume.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  act(() => window.speechSynthesis.speak.mock.calls[1][0].onerror({ error: "interrupted" }));
  expect(screen.getByText(/Audio was interrupted/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Listen" })).toBeTruthy();
});

it("offers manual playback when autoplay is blocked and dismisses volume help after five seconds", async () => {
  vi.useFakeTimers();
  render(<GuidanceAnswer message={message} />);
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  act(() => window.speechSynthesis.speak.mock.calls[0][0].onerror({ error: "not-allowed" }));
  expect(screen.getByText(/Playback was blocked/)).toBeTruthy();
  expect(screen.getByText("Can't hear the guidance? Check your device volume.")).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(4999); });
  expect(screen.getByRole("button", { name: "Dismiss audio help" })).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(screen.queryByRole("button", { name: "Dismiss audio help" })).toBeNull();
  expect(screen.getByRole("button", { name: "Listen" })).toBeTruthy();
  expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1);
});

it("lets volume help be dismissed and recovers from a silent audio engine", async () => {
  vi.useFakeTimers();
  render(<GuidanceAnswer message={message} />);
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
  expect(screen.getByText(/Audio did not start/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Dismiss audio help" }));
  expect(screen.queryByText("Can't hear the guidance? Check your device volume.")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(2);
});

it("stops an older answer before playing another and ignores stale callbacks", () => {
  const view = render(<><GuidanceAnswer message={message} /><GuidanceAnswer message={{ ...message, id: "answer-2", text: "Sing gently." }} /></>);
  fireEvent.click(screen.getAllByRole("button", { name: "Listen" })[0]);
  const first = window.speechSynthesis.speak.mock.calls[0][0];
  const staleEnd = first.onend;
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  expect(first.onend).toBeNull();
  act(() => staleEnd());
  expect(screen.getAllByRole("button", { name: "Stop audio" })).toHaveLength(1);
  view.unmount();
  expect(window.speechSynthesis.speak.mock.calls[1][0].onstart).toBeNull();
});

it("cancels pending presentation on navigation and never autoplays saved replies", async () => {
  vi.useFakeTimers();
  const view = render(<GuidanceAnswer message={message} fresh />);
  view.rerender(<GuidanceAnswer message={message} fresh active={false} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  view.rerender(<GuidanceAnswer message={message} fresh />);
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(window.speechSynthesis.speak).not.toHaveBeenCalled();
  view.unmount();
  render(<GuidanceAnswer message={message} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(window.speechSynthesis.speak).not.toHaveBeenCalled();
  expect(screen.getByText(message.text)).toBeTruthy();
});

it("keeps manual Listen and Stop available with autoplay off and applies enabling to new replies", async () => {
  vi.useFakeTimers();
  const view = render(<GuidanceAnswer message={message} fresh automaticPlayback={false} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(window.speechSynthesis.speak).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Stop audio" }));
  view.rerender(<GuidanceAnswer message={message} fresh automaticPlayback />);
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1);
  view.rerender(<GuidanceAnswer key="next" message={{ ...message, id: "next", text: "Sing gently." }} fresh automaticPlayback />);
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(2);
});

it("stops automatic audio when disabled while preserving manual playback and navigation cleanup", async () => {
  vi.useFakeTimers();
  const view = render(<GuidanceAnswer message={message} fresh />);
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  const automatic = window.speechSynthesis.speak.mock.calls[0][0];
  view.rerender(<GuidanceAnswer message={message} fresh automaticPlayback={false} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(automatic.onstart).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  const manual = window.speechSynthesis.speak.mock.calls[1][0];
  view.rerender(<GuidanceAnswer message={message} fresh automaticPlayback />);
  view.rerender(<GuidanceAnswer message={message} fresh automaticPlayback={false} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(manual.onstart).not.toBeNull();
  expect(screen.getByRole("button", { name: "Stop audio" })).toBeTruthy();
  view.rerender(<GuidanceAnswer message={message} fresh automaticPlayback={false} active={false} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(manual.onstart).toBeNull();
  expect(screen.getByRole("button", { name: "Listen" }).disabled).toBe(true);
});

it("respects reduced motion, preserves formatted content and never executes markup", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
  const text = "### Try this\n\n- **Talk** gently.\n- See [a guide](https://example.test/guide).\n<script>alert(1)</script>";
  const view = render(<GuidanceAnswer message={{ ...message, text }} fresh />);
  expect(view.container.querySelector(".guidance-word--pending")).toBeNull();
  expect(screen.getByRole("heading", { name: "Try this" })).toBeTruthy();
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  expect(screen.getByRole("link", { name: "a guide" }).href).toBe("https://example.test/guide");
  expect(view.container.querySelector("script")).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(10); });
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(window.speechSynthesis.speak.mock.calls[0][0].text).toBe("Try this\n\nTalk gently.\nSee a guide.\n<script>alert(1)</script>");
});

it("saves a numeric rating and reasons without inventing a boolean value", async () => {
  render(<GuidanceAnswer message={message} childName="Baby" conversationId="chat-1" />);
  expect(screen.getByText(/Administrators can read your comment/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Helpfulness rating"), { target: { value: "2" } });
  fireEvent.click(screen.getByText("Add an optional reason"));
  fireEvent.click(screen.getByLabelText("Repeated advice"));
  fireEvent.change(screen.getByLabelText("Optional comment"), { target: { value: "The same idea was repeated." } });
  expect(screen.queryByRole("button", { name: "Helpful" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Not helpful" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Save feedback" }));
  await waitFor(() => expect(sendFeedback).toHaveBeenCalledWith("answer-1", {
    rating: 2, reasons: ["repeated_advice"], comment: "The same idea was repeated.", conversation_id: "chat-1",
  }));
  expect(sendFeedback.mock.calls[0][1]).not.toHaveProperty("helpful");
  await screen.findByText(/your feedback was saved/);
});

it("keeps historical boolean feedback without choosing a numeric equivalent", () => {
  render(<GuidanceAnswer message={{ ...message, feedback: { helpful: true } }} conversationId="chat-1" />);
  expect(screen.getByLabelText("Helpfulness rating").value).toBe("");
  expect(screen.getByRole("button", { name: "Save feedback" }).disabled).toBe(true);
});

it("lets a caregiver edit a saved numeric rating through the existing feedback path", async () => {
  render(<GuidanceAnswer message={{ ...message, feedback: { rating: 2, reasons: ["unclear"] } }} conversationId="chat-1" />);
  expect(screen.getByLabelText("Helpfulness rating").value).toBe("2");
  fireEvent.change(screen.getByLabelText("Helpfulness rating"), { target: { value: "5" } });
  fireEvent.click(screen.getByRole("button", { name: "Save feedback" }));
  await waitFor(() => expect(sendFeedback).toHaveBeenCalledWith("answer-1", {
    rating: 5, reasons: ["unclear"], comment: null, conversation_id: "chat-1",
  }));
  await screen.findByText(/your feedback was saved/);
});

it("shows an error and allows retry when feedback fails", async () => {
  sendFeedback.mockRejectedValueOnce(new Error("Please retry."));
  render(<GuidanceAnswer message={message} conversationId="chat-1" />);
  fireEvent.change(screen.getByLabelText("Helpfulness rating"), { target: { value: "5" } });
  fireEvent.click(screen.getByRole("button", { name: "Save feedback" }));
  await screen.findByText("Please retry.");
  expect(screen.getByRole("button", { name: "Save feedback" }).disabled).toBe(false);
});

it.each([
  ["clarification", "Tell me a little more"], ["unrelated", "Baby-care topics only"],
  ["professional_referral", "Professional advice needed"], ["insufficient_references", "More information needed"],
  ["age_out_of_scope", "Supported age range"],
])("labels the %s outcome without claiming guidance was generated", (kind, heading) => {
  render(<GuidanceAnswer message={{ ...message, status: "no_evidence", response_kind: kind }} />);
  expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
  expect(screen.getByText("Response time: 1.00 seconds.")).toBeTruthy();
});
