import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AccountPage from "../../frontend/src/pages/AccountPage";
import { getAccountSecurityStatus } from "../../frontend/src/services/auth";
import { listChildren, updateChild } from "../../frontend/src/services/caregiving";
import { readChildSelection, saveChildSelection } from "../../frontend/src/services/childSelection";

vi.mock("../../frontend/src/hooks/useAuth", () => ({ useAuth: () => ({ user: { uid: "account" }, logout: vi.fn() }) }));
vi.mock("../../frontend/src/services/auth", () => ({
  getAccountSecurityStatus: vi.fn(), resendVerificationEmail: vi.fn(), beginTotpEnrollment: vi.fn(),
  confirmTotpEnrollment: vi.fn(), reauthenticateAccount: vi.fn(), completeTotpSignIn: vi.fn(),
  totpSignInFactors: vi.fn(), turnOffMfa: vi.fn(),
}));
vi.mock("../../frontend/src/services/caregiving", () => ({
  listChildren: vi.fn(), updateChild: vi.fn(), createChild: vi.fn(), deleteChild: vi.fn(),
  deleteAccount: vi.fn(), deleteMyData: vi.fn(),
}));
vi.mock("../../frontend/src/components/AccountConsent", () => ({ default: () => null }));
const child = { id: "child", name: "Example child", date_of_birth: "2025-05-05", age_label: "18 months",
  milestones: ["Uses a spoon"], baseline_milestones: [], health_details: {}, health_context_available: true };
const original = Object.fromEntries(["showModal", "close"].map(key => [key, Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, key)]));
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear();
  getAccountSecurityStatus.mockResolvedValue({ emailVerified: true, totpEnrolled: false });
  listChildren.mockResolvedValue([child]);
  for (const name of ["showModal", "close"]) Object.defineProperty(HTMLDialogElement.prototype, name, {
    configurable: true, value() { this.open = name === "showModal"; },
  });
});
afterEach(() => {
  cleanup(); vi.restoreAllMocks();
  for (const [key, descriptor] of Object.entries(original)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, key, descriptor);
    else delete HTMLDialogElement.prototype[key];
  }
});
const show = (role = "caregiver") => render(<AccountPage accountAccess={{ verified: true, role }} />);

it("loads profiles only on opening and edits through the shared popup without changing chat selection", async () => {
  saveChildSelection("account", "chat-child");
  const changed = vi.fn();
  window.addEventListener("child-profiles-updated", changed);
  try {
    show();
    await screen.findByRole("heading", { name: "MFA off" });
    expect(listChildren).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Edit child profiles" }));
    await screen.findByRole("dialog", { name: "Choose child profile" });
    expect(listChildren).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Edit child profile" }));
    expect(screen.getByLabelText("Child name").value).toBe(child.name);
    fireEvent.change(screen.getByLabelText("Child name"), { target: { value: "Updated child" } });
    updateChild.mockResolvedValue({ ...child, name: "Updated child" });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
    expect(updateChild.mock.calls[0][0]).toBe("child");
    expect(updateChild.mock.calls[0][1]).toMatchObject({ name: "Updated child", date_of_birth: child.date_of_birth,
      milestones: child.milestones });
    expect(readChildSelection("account")).toBe("chat-child");
    fireEvent.click(screen.getByRole("button", { name: "Edit child profiles" }));
    await screen.findByRole("button", { name: /Updated child/ });
    expect(listChildren).toHaveBeenCalledTimes(1);
  } finally { window.removeEventListener("child-profiles-updated", changed); }
});

it("does not expose child profiles to administrators", async () => {
  show("administrator");
  await screen.findByRole("heading", { name: "MFA off" });
  expect(screen.queryByRole("button", { name: "Edit child profiles" })).toBeNull();
  expect(listChildren).not.toHaveBeenCalled();
});

it("allows retrying a failed profile load", async () => {
  listChildren.mockRejectedValueOnce(new Error("Profiles unavailable"));
  show();
  fireEvent.click(screen.getByRole("button", { name: "Edit child profiles" }));
  await screen.findByText("Profiles unavailable");
  await waitFor(() => expect(screen.getByRole("button", { name: "Edit child profiles" }).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "Edit child profiles" }));
  await screen.findByRole("dialog", { name: "Choose child profile" });
  expect(listChildren).toHaveBeenCalledTimes(2);
});
