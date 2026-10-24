import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AdminFeedbackSummary from "../../frontend/src/components/AdminFeedbackSummary";
import { getFeedbackAdminAccess, getFeedbackSummary } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({
  getFeedbackAdminAccess: vi.fn(), getFeedbackSummary: vi.fn(),
}));
const descriptors = Object.fromEntries(["showModal", "close"].map(name =>
  [name, Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name)]));
beforeEach(() => {
  vi.resetAllMocks();
  getFeedbackAdminAccess.mockResolvedValue({ allowed: true });
  getFeedbackSummary.mockResolvedValue({ ratings: [{ label: "4 — Helpful", lower: 5, upper: 9 }],
    reasons: [{ label: "Unclear", lower: null, upper: null }], legacy_helpfulness: [] });
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function () { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: function () { this.open = false; } });
});
afterEach(() => {
  cleanup();
  for (const [name, descriptor] of Object.entries(descriptors)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else delete HTMLDialogElement.prototype[name];
  }
});

it("does not show administrator controls or request feedback for ordinary accounts", async () => {
  getFeedbackAdminAccess.mockResolvedValue({ allowed: false });
  render(<AdminFeedbackSummary />);
  await waitFor(() => expect(getFeedbackAdminAccess).toHaveBeenCalledOnce());
  expect(screen.queryByRole("button")).toBeNull();
  expect(getFeedbackSummary).not.toHaveBeenCalled();
});

it("loads only on opening and displays count bands rather than private records", async () => {
  render(<AdminFeedbackSummary />);
  const button = await screen.findByRole("button", { name: "View feedback overview" });
  expect(getFeedbackSummary).not.toHaveBeenCalled();
  fireEvent.click(button);
  expect(await screen.findByText("5–9 caregivers")).toBeTruthy();
  expect(screen.getByText("Not enough grouped feedback")).toBeTruthy();
  expect(screen.queryByRole("link")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(screen.queryByText("5–9 caregivers")).toBeNull();
});

it("shows a generic failure and allows retry without displaying exception details", async () => {
  getFeedbackSummary.mockRejectedValueOnce(new Error("PRIVATE_INTERNAL_ERROR"));
  render(<AdminFeedbackSummary />);
  fireEvent.click(await screen.findByRole("button", { name: "View feedback overview" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Feedback summary could not be loaded. Please try again.");
  expect(screen.queryByText("PRIVATE_INTERNAL_ERROR")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Retry summary" }));
  expect(await screen.findByText("5–9 caregivers")).toBeTruthy();
});

it("removes administrator controls and results when access is refused", async () => {
  getFeedbackSummary.mockRejectedValue(Object.assign(new Error("denied"), { status: 403 }));
  render(<AdminFeedbackSummary />);
  fireEvent.click(await screen.findByRole("button", { name: "View feedback overview" }));
  await waitFor(() => expect(screen.queryByRole("button")).toBeNull());
  expect(screen.queryByText("5–9 caregivers")).toBeNull();
});
