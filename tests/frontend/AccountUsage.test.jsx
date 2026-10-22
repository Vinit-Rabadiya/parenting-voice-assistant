import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AccountUsage from "../../frontend/src/components/AccountUsage";
import { getAccountUsage } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({ getAccountUsage: vi.fn() }));
const originalDialogMethods = Object.fromEntries(["showModal", "close"].map((name) => [name, Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name)]));
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function () { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: function () { this.open = false; } });
});
afterEach(() => {
  cleanup(); vi.resetAllMocks();
  for (const [name, descriptor] of Object.entries(originalDialogMethods)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else delete HTMLDialogElement.prototype[name];
  }
});

it("shows allowances and refreshes only on request", async () => {
  getAccountUsage.mockResolvedValue({ as_of: "2026-10-21T12:00:00Z", items: [{
    action: "coaching",
    hourly: { used: 4, limit: 30, remaining: 26, resets_at: "2026-10-21T13:00:00Z" },
    daily: { used: 12, limit: 100, remaining: 88, resets_at: "2026-10-21T21:00:00Z" },
  }] });
  render(<AccountUsage />);
  expect(getAccountUsage).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "View usage" }));
  expect(await screen.findByText(/4 of 30 this hour/)).toBeTruthy();
  expect(screen.getByText(/12 of 100 today/)).toBeTruthy();
  expect(getAccountUsage).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Refresh usage" }));
  await waitFor(() => expect(getAccountUsage).toHaveBeenCalledTimes(2));
});

it("shows a retry option rather than invented zero counts on failure", async () => {
  getAccountUsage.mockRejectedValue(new Error("offline"));
  render(<AccountUsage />);
  fireEvent.click(screen.getByRole("button", { name: "View usage" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Usage could not be loaded. Please try again.");
  expect(screen.queryByText(/\d+ remaining/)).toBeNull();
  expect(screen.getByRole("button", { name: "Refresh usage" }).disabled).toBe(false);
});
