import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AccountPage from "../../frontend/src/pages/AccountPage";
import { beginTotpEnrollment, confirmTotpEnrollment, getAccountSecurityStatus,
  reauthenticateAccount, completeTotpSignIn } from "../../frontend/src/services/auth";
import QRCode from "qrcode";

vi.mock("../../frontend/src/hooks/useAuth", () => ({ useAuth: () => ({
  user: { uid: "test-account", email: "account@example.test" }, logout: vi.fn(),
}) }));
vi.mock("../../frontend/src/services/auth", () => ({
  beginTotpEnrollment: vi.fn(), confirmTotpEnrollment: vi.fn(), getAccountSecurityStatus: vi.fn(),
  reauthenticateAccount: vi.fn(), completeTotpSignIn: vi.fn(), totpSignInFactors: () => [],
  turnOffMfa: vi.fn(), resendVerificationEmail: vi.fn(),
}));
vi.mock("qrcode", () => ({ default: { toDataURL: vi.fn() } }));
vi.mock("../../frontend/src/services/caregiving", () => ({ deleteMyData: vi.fn(), deleteAccount: vi.fn() }));
vi.mock("../../frontend/src/components/AccountUsage", () => ({ default: () => <p>Caregiver usage</p> }));
vi.mock("../../frontend/src/components/AccountConsent", () => ({ default: () => <p>Caregiver consent</p> }));

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  getAccountSecurityStatus.mockResolvedValue({ emailVerified: true, totpEnrolled: true,
    mfaRequired: false, factorCount: 1, usesGoogle: true });
  reauthenticateAccount.mockResolvedValue({ next: "signed-in" });
  beginTotpEnrollment.mockResolvedValue({ userId: "test-account", secret: {
    secretKey: "example-test-key", generateQrCodeUrl: () => "otpauth://test-only",
  } });
  QRCode.toDataURL.mockResolvedValue("data:image/png;base64,test-only");
});
afterEach(cleanup);

it("keeps administrator account settings separate from caregiver tools", async () => {
  render(<AccountPage email="account@example.test" accountAccess={{ verified: true, role: "administrator" }} />);
  await screen.findByRole("heading", { name: "MFA enabled" });
  expect(screen.queryByText("Caregiver usage")).toBeNull();
  expect(screen.queryByText("Caregiver consent")).toBeNull();
  expect(screen.queryByRole("switch", { name: /Read replies automatically/ })).toBeNull();
  expect(screen.getByRole("button", { name: "Delete my account" })).toBeTruthy();
});

it("remembers the caregiver playback setting when My Account is reopened", async () => {
  const account = <AccountPage email="account@example.test" accountAccess={{ verified: true }} />;
  const view = render(account);
  const setting = await screen.findByRole("switch", { name: /Read replies automatically/ });
  expect(setting.checked).toBe(true);
  fireEvent.click(setting);
  expect(setting.checked).toBe(false);
  view.unmount();
  render(account);
  expect((await screen.findByRole("switch", { name: /Read replies automatically/ })).checked).toBe(false);
});

it("applies playback choices in the tab and explains when the browser cannot save them", async () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Storage blocked"); });
  try {
    render(<AccountPage email="account@example.test" accountAccess={{ verified: true }} />);
    const setting = await screen.findByRole("switch", { name: /Read replies automatically/ });
    fireEvent.click(setting);
    expect(setting.checked).toBe(false);
    expect(screen.getByText(/Your choice applies to this tab/)).toBeTruthy();
    // Restore the initial choice without requiring a persistent write.
    fireEvent.click(setting);
  } finally { vi.restoreAllMocks(); }
});

async function openSetup() {
  render(<AccountPage email="account@example.test" accountAccess={{ verified: true }} />);
  fireEvent.click(await screen.findByRole("button", { name: "Add backup authenticator" }));
}

it("confirms the current sign-in before starting backup setup", async () => {
  await openSetup();
  expect(screen.getByText(/Your authenticator protects sign-in/)).toBeTruthy();
  expect(beginTotpEnrollment).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
  await screen.findByText("example-test-key");
  expect(reauthenticateAccount).toHaveBeenCalledWith("", "test-account");
  expect(beginTotpEnrollment).toHaveBeenCalledTimes(1);
  expect(confirmTotpEnrollment).not.toHaveBeenCalled();
});

it("also confirms sign-in before adding the first authenticator", async () => {
  getAccountSecurityStatus.mockResolvedValue({ emailVerified: true, totpEnrolled: false,
    mfaRequired: false, factorCount: 0, usesGoogle: true });
  render(<AccountPage email="account@example.test" accountAccess={{ verified: true }} />);
  fireEvent.click(await screen.findByRole("button", { name: "Set up authenticator" }));
  expect(beginTotpEnrollment).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
  await screen.findByText("example-test-key");
  expect(reauthenticateAccount).toHaveBeenCalledTimes(1);
});

it("requires the existing MFA challenge before creating another setup key", async () => {
  reauthenticateAccount.mockResolvedValue({ next: "mfa-required", resolver: {} });
  completeTotpSignIn.mockResolvedValue({ uid: "test-account" });
  await openSetup();
  fireEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
  const input = await screen.findByLabelText("Authenticator code");
  expect(beginTotpEnrollment).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: "012345" } });
  fireEvent.click(screen.getByRole("button", { name: "Verify code" }));
  await screen.findByText("example-test-key");
  expect(completeTotpSignIn).toHaveBeenCalledWith({}, "012345", null);
});

it("keeps manual enrollment available if QR rendering fails", async () => {
  QRCode.toDataURL.mockRejectedValue(new Error("Test renderer failure"));
  await openSetup();
  fireEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
  await screen.findByText(/Use the setup key below/);
  expect(screen.getByText("example-test-key")).toBeTruthy();
  expect(screen.queryByRole("img", { name: /QR code/ })).toBeNull();
  fireEvent.change(screen.getByLabelText("Authenticator code"), { target: { value: "012345" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm authenticator" }));
  await waitFor(() => expect(confirmTotpEnrollment).toHaveBeenCalledWith(expect.anything(), "012345"));
});

it.each([
  ["auth/network-request-failed", "Check your internet connection"],
  ["auth/operation-not-allowed", "Authenticator setup is unavailable"],
  ["auth/invalid-multi-factor-session", "Authenticator setup expired"],
])("shows an actionable %s error without exposing provider details", async (code, expected) => {
  beginTotpEnrollment.mockRejectedValue(Object.assign(new Error("PRIVATE setup-key and credentials"), { code }));
  await openSetup();
  fireEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
  await screen.findByText(new RegExp(expected));
  expect(screen.queryByText(/PRIVATE/)).toBeNull();
  expect(screen.getByText(code)).toBeTruthy();
  expect(screen.getByRole("heading", { name: "MFA enabled" })).toBeTruthy();
});

it("cancels confirmation without creating an authenticator", async () => {
  await openSetup();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(beginTotpEnrollment).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Continue with Google" })).toBeNull();
});

it("discards expired setup and confirms sign-in again before retrying", async () => {
  confirmTotpEnrollment.mockRejectedValue(Object.assign(new Error("Expired test session"), {
    code: "auth/invalid-multi-factor-session",
  }));
  await openSetup();
  fireEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
  await screen.findByText("example-test-key");
  fireEvent.change(screen.getByLabelText("Authenticator code"), { target: { value: "012345" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm authenticator" }));
  await screen.findByText(/Authenticator setup expired/);
  expect(screen.queryByText("example-test-key")).toBeNull();
  expect(screen.getByRole("button", { name: "Continue with Google" })).toBeTruthy();
});
