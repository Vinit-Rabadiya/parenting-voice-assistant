import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AdminFeedbackSummary from "../../frontend/src/components/AdminFeedbackSummary";
import { getFeedbackSummary } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({ getFeedbackSummary: vi.fn() }));
const report = { unit: "Saved feedback per answer",
  ratings: [{ label: "4 — Helpful", count: 1 }],
  reasons: [{ label: "Unclear", count: 0 }], legacy_helpfulness: [], comments: [], comment_count: 0 };
beforeEach(() => { vi.resetAllMocks(); getFeedbackSummary.mockResolvedValue(report); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

it("shows the first saved rating without a caregiver minimum", async () => {
  render(<AdminFeedbackSummary />);
  expect(await screen.findByText("1")).toBeTruthy();
  expect(screen.getByText("response")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Helpfulness ratings" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Feedback reasons" })).toBeTruthy();
  expect(screen.getByText("0")).toBeTruthy();
  expect(screen.queryByText("No feedback yet")).toBeNull();
  expect(screen.queryByText(/at least five/)).toBeNull();
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.queryByRole("link")).toBeNull();
  expect(screen.queryByText("Earlier feedback")).toBeNull();
  expect(getFeedbackSummary).toHaveBeenCalledTimes(1);
});

it("refreshes on request and does not reload on ordinary rerenders", async () => {
  let complete;
  getFeedbackSummary.mockResolvedValueOnce(report).mockReturnValueOnce(new Promise(resolve => { complete = resolve; }));
  const view = render(<AdminFeedbackSummary />);
  await screen.findByText("1");
  view.rerender(<AdminFeedbackSummary />);
  expect(getFeedbackSummary).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Refresh feedback" }));
  expect(screen.queryByText("1")).toBeNull();
  expect(screen.getByRole("button", { name: "Refresh feedback" }).disabled).toBe(true);
  await act(async () => complete({ ...report, ratings: [{ label: "4 — Helpful", count: 2 }] }));
  expect(await screen.findByText("2")).toBeTruthy();
  expect(getFeedbackSummary).toHaveBeenCalledTimes(2);
});

it("shows an empty state and zero counts when there is no saved feedback", async () => {
  getFeedbackSummary.mockResolvedValue({ ...report, ratings: [{ label: "4 — Helpful", count: 0 }] });
  render(<AdminFeedbackSummary />);
  expect(await screen.findByRole("heading", { name: "No feedback yet" })).toBeTruthy();
  expect(screen.getAllByText("0")).toHaveLength(2);
});

it("shows a generic failure and allows retry without displaying exception details", async () => {
  getFeedbackSummary.mockRejectedValueOnce(new Error("PRIVATE_INTERNAL_ERROR"));
  render(<AdminFeedbackSummary />);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Feedback could not be loaded. Please try again.");
  expect(screen.queryByText("PRIVATE_INTERNAL_ERROR")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("1")).toBeTruthy();
});

it("clears previous results if administrator permission is refused on refresh", async () => {
  getFeedbackSummary.mockResolvedValueOnce(report).mockRejectedValueOnce(Object.assign(new Error("denied"), { status: 403 }));
  render(<AdminFeedbackSummary />);
  await screen.findByText("1");
  fireEvent.click(screen.getByRole("button", { name: "Refresh feedback" }));
  await screen.findByText(/Administrator access is unavailable/);
  expect(screen.queryByText("1")).toBeNull();
  expect(screen.getByRole("button", { name: "Refresh feedback" }).disabled).toBe(true);
});

it.each([-1, 1.5, "1", true, null])("rejects an invalid category count: %s", async count => {
  getFeedbackSummary.mockResolvedValue({ ...report, ratings: [{ label: "Invalid category", count }] });
  render(<AdminFeedbackSummary />);
  await screen.findByRole("alert");
  expect(screen.queryByText("Invalid category")).toBeNull();
});

it("times out an unresponsive request and ignores its late result", async () => {
  vi.useFakeTimers();
  let complete;
  getFeedbackSummary.mockReturnValue(new Promise(resolve => { complete = resolve; }));
  render(<AdminFeedbackSummary />);
  const signal = getFeedbackSummary.mock.calls[0][0];
  await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
  expect(screen.getByText(/Feedback took too long/)).toBeTruthy();
  expect(signal.aborted).toBe(true);
  await act(async () => complete(report));
  expect(screen.queryByText("1")).toBeNull();
});

it("keeps earlier binary ratings separate even when there is only one response", async () => {
  getFeedbackSummary.mockResolvedValue({ ...report, legacy_helpfulness: [{ label: "Helpful", count: 1 }] });
  render(<AdminFeedbackSummary />);
  const toggle = await screen.findByText("Earlier feedback");
  expect(toggle.closest("details").open).toBe(false);
  fireEvent.click(toggle);
  expect(toggle.closest("details").open).toBe(true);
});

it("shows written feedback with rating and reasons as plain text without conversation links", async () => {
  getFeedbackSummary.mockResolvedValue({ ...report, comment_count: 1,
    comments: [{ comment: "<img src=x onerror=alert(1)> The reply repeated the same advice.", rating: 2,
      helpful: null, reasons: ["Repeated advice"] }] });
  render(<AdminFeedbackSummary />);
  await screen.findByText(/The reply repeated the same advice/);
  expect(screen.getByText("Rating: 2 / 5")).toBeTruthy();
  expect(screen.getByText("Repeated advice")).toBeTruthy();
  expect(screen.queryByRole("img")).toBeNull();
  expect(screen.queryByRole("link")).toBeNull();
});

it("removes previous comments when a refresh returns edited or deleted feedback", async () => {
  getFeedbackSummary.mockResolvedValueOnce({ ...report, comment_count: 1,
    comments: [{ comment: "Earlier feedback.", rating: 2, helpful: null, reasons: [] }] })
    .mockResolvedValueOnce(report);
  render(<AdminFeedbackSummary />);
  await screen.findByText("Earlier feedback.");
  fireEvent.click(screen.getByRole("button", { name: "Refresh feedback" }));
  await screen.findByText("No written feedback has been shared yet.");
  expect(screen.queryByText("Earlier feedback.")).toBeNull();
});
