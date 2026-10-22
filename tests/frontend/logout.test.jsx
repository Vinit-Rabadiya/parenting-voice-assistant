import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthProvider } from "../../frontend/src/context/AuthProvider";
import { useAuth } from "../../frontend/src/hooks/useAuth";
import AccountPage from "../../frontend/src/pages/AccountPage";
import { Navbar } from "../../frontend/src/components/Navbar";
import { deleteMyData } from "../../frontend/src/services/caregiving";

const { user, logOut, unsubscribe } = vi.hoisted(() => ({
  user: { uid: "caregiver", email: "caregiver@example.test" },
  logOut: vi.fn(),
  unsubscribe: vi.fn(),
}));

vi.mock("../../frontend/src/services/firebase", () => ({
  auth: { onAuthStateChanged: (callback) => { callback(user); return unsubscribe; } },
}));
vi.mock("../../frontend/src/services/api", () => ({ getCurrentAccount: vi.fn() }));
vi.mock("../../frontend/src/services/caregiving", () => ({ deleteMyData: vi.fn(), deleteAccount: vi.fn() }));
vi.mock("../../frontend/src/services/auth", () => ({
  logOut,
  getAccountSecurityStatus: async () => ({ emailVerified: true, totpEnrolled: true }),
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
  deleteMyData.mockReset();
  logOut.mockReset();
  logOut.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("deletes saved data after confirmation without logging out", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  deleteMyData.mockResolvedValue(undefined);
  render(<AuthProvider><AccountHarness /></AuthProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Delete my data" }));
  await screen.findByText(/Your saved app data was deleted/);
  expect(deleteMyData).toHaveBeenCalledTimes(1);
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
