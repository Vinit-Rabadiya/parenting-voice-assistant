import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readChildSelection, saveChildSelection } from "../../frontend/src/services/childSelection";
import { AuthProvider } from "../../frontend/src/context/AuthProvider";
import { useAuth } from "../../frontend/src/hooks/useAuth";
import AccountPage from "../../frontend/src/pages/AccountPage";
import { Navbar } from "../../frontend/src/components/Navbar";
import { deleteMyData, deleteAccount } from "../../frontend/src/services/caregiving";
import { getAccountSecurityStatus, reauthenticateAccount, turnOffMfa } from "../../frontend/src/services/auth";
import usePlaybackPreference from "../../frontend/src/hooks/usePlaybackPreference";

const { user, logOut, unsubscribe, authListener } = vi.hoisted(() => ({
  user: { uid: "caregiver", email: "caregiver@example.test" },
  authListener: { current: null },
  logOut: vi.fn(),
  unsubscribe: vi.fn(),
}));

vi.mock("../../frontend/src/services/firebase", () => ({
  auth: { onAuthStateChanged: (callback) => { authListener.current = callback; callback(user); return unsubscribe; } },
}));
vi.mock("../../frontend/src/services/api", () => ({ getCurrentAccount: vi.fn() }));
vi.mock("../../frontend/src/services/caregiving", () => ({ deleteMyData: vi.fn(), deleteAccount: vi.fn() }));
vi.mock("../../frontend/src/services/auth", () => ({
  logOut,
  getAccountSecurityStatus: vi.fn(),
  reauthenticateAccount: vi.fn(), turnOffMfa: vi.fn(),
  completeTotpSignIn: vi.fn(), totpSignInFactors: vi.fn(() => []),
  resendVerificationEmail: vi.fn(),
  beginTotpEnrollment: vi.fn(),
  confirmTotpEnrollment: vi.fn(),
}));

// expose provider state while using the real account page logout button.
function AccountHarness() {
  const account = useAuth();
  return (
    <>
      <button onClick={() => account.setSignupResult({ user, verificationEmailRequested: true })}>
        Set signup result
      </button>
      <p data-testid="account-state">{account.user?.uid ?? "signed out"}</p>
      <p data-testid="signup-state">{account.signupResult ? "present" : "cleared"}</p>
      {account.user && <><Navbar isAuthenticated onAccount={() => {}} />
        <AccountPage email={account.user.email} accountAccess={{ verified: true, checking: false, error: "" }} /></>}
    </>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  deleteMyData.mockReset();
  logOut.mockReset();
  logOut.mockResolvedValue(undefined);
  getAccountSecurityStatus.mockResolvedValue({ emailVerified: true, totpEnrolled: true,
    mfaRequired: false, usesGoogle: true, factorCount: 1 });
  reauthenticateAccount.mockResolvedValue({ next: "signed-in" });
  turnOffMfa.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("keeps MFA optional and disables it only after confirming sign-in", async () => {
  render(<AuthProvider><AccountHarness /></AuthProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Turn off MFA" }));
  expect(turnOffMfa).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Continue with Google" }));
  await waitFor(() => expect(turnOffMfa).toHaveBeenCalledWith("caregiver"));
  expect(reauthenticateAccount).toHaveBeenCalledWith("", "caregiver");
  await waitFor(() => expect(logOut).toHaveBeenCalledTimes(1));
});

it("explains mandatory MFA and prevents turning it off", async () => {
  getAccountSecurityStatus.mockResolvedValue({ emailVerified: true, totpEnrolled: true,
    mfaRequired: true, factorCount: 1 });
  render(<AuthProvider><AccountHarness /></AuthProvider>);
  expect((await screen.findByRole("button", { name: "Turn off MFA" })).disabled).toBe(true);
  expect(screen.getByText(/MFA is required by security policy/)).toBeTruthy();
  expect(turnOffMfa).not.toHaveBeenCalled();
});

it("deletes saved data after confirmation without logging out", async () => {
  const preference = renderHook(() => usePlaybackPreference("caregiver"));
  act(() => preference.result.current.setAutomatic(false));
  vi.spyOn(window, "confirm").mockReturnValue(true);
  deleteMyData.mockResolvedValue(undefined);
  render(<AuthProvider><AccountHarness /></AuthProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Delete my data" }));
  await screen.findByText(/Your saved app data was deleted/);
  expect(deleteMyData).toHaveBeenCalledTimes(1);
  expect(preference.result.current.automatic).toBe(true);
  expect(logOut).not.toHaveBeenCalled();
  expect(screen.getByTestId("account-state").textContent).toBe("caregiver");
  expect(screen.getByRole("region", { name: "MFA enabled" })).toBeTruthy();
  expect(screen.getByRole("region", { name: "Data and account" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Delete my data" }).disabled).toBe(true);
});

it("does not delete data when confirmation is cancelled", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<AuthProvider><AccountHarness /></AuthProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Delete my data" }));
  expect(deleteMyData).not.toHaveBeenCalled();
});

it("keeps the login active and allows retry after data deletion fails", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  deleteMyData.mockRejectedValue(new Error("Data deletion could not finish. Please retry."));
  render(<AuthProvider><AccountHarness /></AuthProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Delete my data" }));
  await screen.findByText("Data deletion could not finish. Please retry.");
  expect(screen.getByRole("button", { name: "Delete my data" }).disabled).toBe(false);
  expect(logOut).not.toHaveBeenCalled();
});

// the page uses provider logout so account and signup state are cleared together.
it("clears account state and onboarding data after successful logout", async () => {
  const preference = renderHook(() => usePlaybackPreference("caregiver"));
  act(() => preference.result.current.setAutomatic(false));
  const { unmount } = render(<AuthProvider><AccountHarness /></AuthProvider>);
  fireEvent.click(screen.getByRole("button", { name: "Set signup result" }));
  expect(screen.getByTestId("signup-state").textContent).toBe("present");
  fireEvent.click(screen.getByRole("button", { name: "My Account" }));
  const logoutButton = await screen.findByRole("button", { name: "Log Out" });
  expect(screen.getByText("Verified")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Check backend access" })).toBeNull();
  expect(screen.queryByText(/Log out and test MFA/)).toBeNull();
  fireEvent.click(logoutButton);
  await waitFor(() => expect(screen.getByTestId("account-state").textContent).toBe("signed out"));
  expect(screen.getByTestId("signup-state").textContent).toBe("cleared");
  expect(preference.result.current.automatic).toBe(false);
  expect(logOut).toHaveBeenCalledOnce();
  unmount();
  expect(unsubscribe).toHaveBeenCalledOnce();
});

// a failed logout leaves the current account intact and allows retry.
it("preserves state on logout failure and clears it after retry", async () => {
  logOut.mockRejectedValueOnce(new Error("sign out failed"));
  render(<AuthProvider><AccountHarness /></AuthProvider>);
  fireEvent.click(screen.getByRole("button", { name: "Set signup result" }));
  fireEvent.click(screen.getByRole("button", { name: "My Account" }));
  fireEvent.click(await screen.findByRole("button", { name: "Log Out" }));
  await screen.findByText("Could not log out. Please try again.");
  expect(screen.getByTestId("account-state").textContent).toBe("caregiver");
  expect(screen.getByTestId("signup-state").textContent).toBe("present");
  fireEvent.click(screen.getByRole("button", { name: "Log Out" }));
  await waitFor(() => expect(screen.getByTestId("account-state").textContent).toBe("signed out"));
  expect(screen.getByTestId("signup-state").textContent).toBe("cleared");
  expect(logOut).toHaveBeenCalledTimes(2);
});

it("clears the remembered child only after successful logout", async () => {
  saveChildSelection("caregiver", "child-id");
  logOut.mockRejectedValueOnce(new Error("Try again"));
  render(<AuthProvider><AccountHarness /></AuthProvider>);
  fireEvent.click(screen.getByRole("button", { name: "My Account" }));
  fireEvent.click(screen.getByRole("button", { name: "Log Out" }));
  await screen.findByText("Could not log out. Please try again.");
  expect(readChildSelection("caregiver")).toBe("child-id");
  fireEvent.click(screen.getByRole("button", { name: "Log Out" }));
  await waitFor(() => expect(readChildSelection("caregiver")).toBeNull());
});

it("clears the previous account selection on authentication changes", async () => {
  saveChildSelection("caregiver", "first-child");
  saveChildSelection("other-account", "second-child");
  render(<AuthProvider><AccountHarness /></AuthProvider>);
  expect(readChildSelection("caregiver")).toBe("first-child");
  await act(async () => authListener.current({ uid: "other-account", email: "other@example.test" }));
  expect(readChildSelection("caregiver")).toBeNull();
  expect(readChildSelection("other-account")).toBe("second-child");
  await act(async () => authListener.current(null));
  expect(readChildSelection("other-account")).toBeNull();
});

it("clears the selected child after account deletion even if logout fails", async () => {
  const preference = renderHook(() => usePlaybackPreference("caregiver"));
  act(() => preference.result.current.setAutomatic(false));
  saveChildSelection("caregiver", "child-id");
  vi.spyOn(window, "confirm").mockReturnValue(true);
  deleteAccount.mockResolvedValue(undefined);
  logOut.mockRejectedValueOnce(new Error("Sign out failed"));
  render(<AuthProvider><AccountHarness /></AuthProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Delete my account" }));
  await waitFor(() => expect(deleteAccount).toHaveBeenCalledOnce());
  await waitFor(() => expect(readChildSelection("caregiver")).toBeNull());
  expect(preference.result.current.automatic).toBe(true);
});
