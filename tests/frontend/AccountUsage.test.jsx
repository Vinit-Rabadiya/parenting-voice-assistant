import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import AccountUsage from "../../frontend/src/components/AccountUsage";
import { getAccountUsage } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({ getAccountUsage: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("shows allowances and refreshes only on request", async () => {
  getAccountUsage.mockResolvedValue({ as_of: "2026-10-21T12:00:00Z", items: [{
    action: "coaching",
    hourly: { used: 4, limit: 30, remaining: 26, resets_at: "2026-10-21T13:00:00Z" },
    daily: { used: 12, limit: 100, remaining: 88, resets_at: "2026-10-21T21:00:00Z" },
  }] });
  render(<AccountUsage />);
  expect(await screen.findByText(/4 of 30 this hour/)).toBeTruthy();
  expect(screen.getByText(/12 of 100 today/)).toBeTruthy();
  expect(getAccountUsage).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Refresh usage" }));
  await waitFor(() => expect(getAccountUsage).toHaveBeenCalledTimes(2));
});

it("shows a retry option rather than invented zero counts on failure", async () => {
  getAccountUsage.mockRejectedValue(new Error("offline"));
  render(<AccountUsage />);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Usage could not be loaded. Please try again.");
  expect(screen.queryByText(/remaining/)).toBeNull();
  expect(screen.getByRole("button", { name: "Refresh usage" }).disabled).toBe(false);
});
