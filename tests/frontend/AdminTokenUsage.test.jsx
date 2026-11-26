import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import AdminTokenUsage from "../../frontend/src/components/AdminTokenUsage";
import { getAdminTokenUsage } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({ getAdminTokenUsage: vi.fn() }));

const counts = { input_tokens: 120, output_tokens: 40, thinking_tokens: 10, total_tokens: 170, model_calls: 3 };
const report = { first_recorded_at: "2026-11-26T00:00:00Z", total: counts, providers: [{ provider: "gemini", ...counts }] };

afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("shows the provider breakdown and refreshes the overall total", async () => {
  getAdminTokenUsage.mockResolvedValueOnce(report).mockResolvedValueOnce({ ...report,
    total: { ...counts, input_tokens: 130, output_tokens: 45, total_tokens: 185, model_calls: 4 },
    providers: [...report.providers, { provider: "groq", input_tokens: 10, output_tokens: 5, thinking_tokens: 0,
      total_tokens: 15, model_calls: 1 }],
  });
  render(<AdminTokenUsage />);
  await screen.findByRole("rowheader", { name: "Gemini" });
  const overall = () => screen.getByRole("rowheader", { name: "Overall" }).closest("tr");
  expect(within(overall()).getByText("170")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Refresh usage" }));
  await screen.findByRole("rowheader", { name: "Groq" });
  expect(within(overall()).getByText("185")).toBeTruthy();
});

it("shows empty tracking and handles an authorization error on refresh", async () => {
  getAdminTokenUsage.mockResolvedValueOnce({ first_recorded_at: null, providers: [],
    total: Object.fromEntries(Object.keys(counts).map(key => [key, 0])),
  }).mockRejectedValueOnce(Object.assign(new Error("Forbidden"), { status: 403 }));
  render(<AdminTokenUsage />);
  await screen.findByText("No model token usage has been recorded yet.");
  fireEvent.click(screen.getByRole("button", { name: "Refresh usage" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Administrator access is required to view token usage.");
  expect(screen.queryByRole("table")).toBeNull();
});
