import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AccountConsent from "../../frontend/src/components/AccountConsent";
import { getPrivacyConsent } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({ getPrivacyConsent: vi.fn() }));
const originalDialogMethods = Object.fromEntries(["showModal", "close"].map((name) => [
  name, Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name),
]));
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true, value: vi.fn(function () { this.open = true; }),
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true, value: vi.fn(function () { this.open = false; }),
  });
});
afterEach(() => {
  cleanup(); vi.resetAllMocks();
  for (const [name, descriptor] of Object.entries(originalDialogMethods)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else delete HTMLDialogElement.prototype[name];
  }
});

it("loads accepted terms only when the button is opened", async () => {
  getPrivacyConsent.mockResolvedValue({ accepted: true, version: "v1", accepted_at: "2026-10-21T12:00:00Z", notice: ["Your messages are stored."] });
  render(<AccountConsent />);
  expect(getPrivacyConsent).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "View accepted consent" }));
  expect(await screen.findByText("Your messages are stored.")).toBeTruthy();
  expect(screen.getByText("You have accepted this privacy notice.")).toBeTruthy();
  expect(screen.getByText(/Accepted on/)).toBeTruthy();
  expect(screen.getByRole("dialog", { name: "Your privacy consent" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("does not describe an unaccepted current notice as accepted", async () => {
  getPrivacyConsent.mockResolvedValue({ accepted: false, version: "v2", notice: ["Updated terms."] });
  render(<AccountConsent />);
  fireEvent.click(screen.getByRole("button", { name: "View accepted consent" }));
  expect(await screen.findByText(/You have not accepted the current privacy notice/)).toBeTruthy();
  expect(screen.queryByText(/Accepted on/)).toBeNull();
});

it("offers retry when consent cannot be read", async () => {
  getPrivacyConsent.mockRejectedValue(new Error("offline"));
  render(<AccountConsent />);
  fireEvent.click(screen.getByRole("button", { name: "View accepted consent" }));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Retry consent details" })).toBeTruthy();
});
