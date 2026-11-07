import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import VaccineLearning from "../../frontend/src/components/VaccineLearning";
import { checkedOn, educationIsCurrent, entries } from "../../frontend/src/content/vaccineLearning";

const originalMethods = Object.fromEntries(["showModal", "close"].map(name =>
  [name, Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name)]));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-06T12:00:00Z"));
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true, value() { this.open = true; },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true, value() { this.open = false; },
  });
  vi.stubGlobal("fetch", vi.fn(() => { throw new Error("Education must not fetch data"); }));
  vi.stubGlobal("SpeechSynthesisUtterance", function (text) { this.text = text; });
  vi.stubGlobal("speechSynthesis", { speak: vi.fn(), cancel: vi.fn() });
});
afterEach(() => {
  cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks();
  for (const [name, descriptor] of Object.entries(originalMethods)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else delete HTMLDialogElement.prototype[name];
  }
});

it("explains booklet abbreviations and searches locally with checked sources", () => {
  render(<VaccineLearning onClose={vi.fn()} onAsk={vi.fn()} />);
  expect(screen.getByText(/BABIES AGED 0–24 MONTHS/)).toBeTruthy();
  expect(screen.getByText("6 November 2026").dateTime).toBe(checkedOn);
  fireEvent.change(screen.getByLabelText("Find a vaccine name or question"), { target: { value: "pcv13" } });
  expect(screen.getByRole("heading", { name: "PCV — pneumococcal" })).toBeTruthy();
  expect(screen.getByText(/PCV means pneumococcal conjugate vaccine/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "UNICEF: Vaccines and the diseases they prevent" }).href)
    .toBe("https://www.unicef.org/parenting/health/vaccines-and-diseases-they-prevent");
  expect(fetch).not.toHaveBeenCalled();
  expect(speechSynthesis.speak).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Find a vaccine name or question"), { target: { value: "no such entry" } });
  expect(screen.getByRole("status").textContent).toContain("No matching explanation");
});

it("provides sourced answers about conflicting claims without generating advice", () => {
  render(<VaccineLearning onClose={vi.fn()} onAsk={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Do vaccines cause autism?" }));
  expect(screen.getByText(/Research has found no link/)).toBeTruthy();
  expect(screen.getByRole("link", { name: /UNICEF: Vaccines for children/ })).toBeTruthy();
  expect(fetch).not.toHaveBeenCalled();
});

it("keeps missing entries and local eligibility separate from dose decisions", () => {
  render(<VaccineLearning onClose={vi.fn()} onAsk={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "What if an entry is missing or unclear?" }));
  expect(screen.getByText(/cannot infer previous doses or calculate a personal catch-up plan/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Malaria — RTS,S and R21" }));
  expect(screen.getByText(/clinic confirms local programme eligibility/)).toBeTruthy();
  // Cards deliberately contain no appointment ages or number of doses.
  expect(entries.some(entry => /\d+\s*(?:weeks?|months?|doses?)/i.test(entry.text))).toBe(false);
});

it("prepares a question only after the parent selects the follow-up action", () => {
  const onAsk = vi.fn();
  const view = render(<VaccineLearning onClose={vi.fn()} onAsk={onAsk} />);
  fireEvent.click(screen.getByRole("button", { name: "PCV — pneumococcal" }));
  expect(onAsk).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Open in new chat" }));
  expect(onAsk).toHaveBeenCalledExactlyOnceWith("What does PCV mean in my baby's vaccination booklet?");
  view.rerender(<VaccineLearning onClose={vi.fn()} onAsk={onAsk} hasDraft />);
  expect(screen.getByRole("button", { name: "Open in new chat" }).disabled).toBe(true);
  view.rerender(<VaccineLearning onClose={vi.fn()} onAsk={onAsk} askDisabled />);
  expect(screen.getByRole("button", { name: "Open in new chat" }).disabled).toBe(true);
});

it("plays only on request and stops when changing explanations or closing", async () => {
  const view = render(<VaccineLearning onClose={vi.fn()} onAsk={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Listen to explanation" }));
  expect(speechSynthesis.speak).toHaveBeenCalledTimes(1);
  expect(speechSynthesis.speak.mock.calls[0][0].text).toContain("Your clinic confirms");
  fireEvent.click(screen.getByRole("button", { name: "BCG" }));
  await waitFor(() => expect(speechSynthesis.cancel).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Listen to explanation" }));
  view.unmount();
  expect(speechSynthesis.cancel).toHaveBeenCalledTimes(2);
});

it("withholds stale or future-dated cards without losing the original source", () => {
  expect(educationIsCurrent(new Date("2026-11-05T12:00:00Z"))).toBe(false);
  expect(educationIsCurrent(new Date("2027-02-04T12:00:00Z"))).toBe(true);
  expect(educationIsCurrent(new Date("2027-02-05T12:00:00Z"))).toBe(false);
  vi.setSystemTime(new Date("2027-03-01T12:00:00Z"));
  render(<VaccineLearning onClose={vi.fn()} onAsk={vi.fn()} />);
  const section = screen.getByRole("region", { name: "Source review needed" });
  expect(within(section).getByRole("link", { name: /WHO/ })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "BCG" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Listen to explanation" })).toBeNull();
});

it("handles Escape, native close and development StrictMode without closing a reopened dialog", () => {
  const onClose = vi.fn();
  document.body.style.overflow = "auto";
  const view = render(<StrictMode><VaccineLearning onClose={onClose} onAsk={vi.fn()} /></StrictMode>);
  const dialog = screen.getByRole("dialog", { name: "Understand my baby's vaccines" });
  expect(document.body.style.overflow).toBe("hidden");
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Close vaccine explanations" }));
  // Native close is queued; an old StrictMode cleanup event must not dismiss a reopened dialog.
  fireEvent(dialog, new Event("close"));
  expect(onClose).not.toHaveBeenCalled();
  fireEvent(dialog, new Event("cancel", { cancelable: true }));
  expect(onClose).toHaveBeenCalledTimes(1);
  act(() => { dialog.open = false; fireEvent(dialog, new Event("close")); });
  expect(onClose).toHaveBeenCalledTimes(2);
  view.unmount();
  expect(document.body.style.overflow).toBe("auto");
  document.body.style.overflow = "";
});
