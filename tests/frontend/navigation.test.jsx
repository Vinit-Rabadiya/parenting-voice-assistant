import { useEffect, useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "../../frontend/src/App";
import AuthPage from "../../frontend/src/pages/AuthPage";
import { completeTotpSignIn } from "../../frontend/src/services/auth";

const { state, microphoneMounted, microphoneReleased } = vi.hoisted(() => ({
  state: { user: null, checkingAuth: false, signupResult: null, setSignupResult: vi.fn(), accessOverride: null, mfaHints: [] },
  microphoneMounted: vi.fn(), microphoneReleased: vi.fn(),
}));

// keep real page navigation and auth form selection, replacing external services.
vi.mock("../../frontend/src/context/AuthProvider", () => ({ AuthProvider: ({ children }) => children }));
vi.mock("../../frontend/src/hooks/useAuth", () => ({ useAuth: () => state }));
vi.mock("../../frontend/src/hooks/useAccountAccess", () => ({
  default: () => state.accessOverride || ({ verified: Boolean(state.user?.emailVerified), checking: false, error: "" }),
}));
vi.mock("../../frontend/src/services/auth", () => ({ completeTotpSignIn: vi.fn(), totpSignInFactors: resolver => resolver.hints }));
vi.mock("../../frontend/src/components/LoginForm", () => ({ default: () => <div>Login form</div> }));
vi.mock("../../frontend/src/components/SignUpForm", () => ({ default: () => <div>Signup form</div> }));
vi.mock("../../frontend/src/components/GoogleSignInButton", () => ({ default: ({ onMfaRequired }) => <button onClick={() => onMfaRequired({ hints: state.mfaHints })}>Google sign in</button> }));
vi.mock("../../frontend/src/pages/AccountPage", () => ({ default: ({ email, verificationEmailRequested, onDataDeleted }) => (
  <div>Account: {email}. Verification requested: {String(verificationEmailRequested)}
    <button onClick={onDataDeleted}>Simulate saved data deletion</button>
  </div>
) }));
vi.mock("../../frontend/src/components/MicrophoneControls", () => ({ default: function FakeMicrophone() {
  useEffect(() => {
    microphoneMounted();
    return () => microphoneReleased();
  }, []);
  return <button>Start recording</button>;
} }));
vi.mock("../../frontend/src/components/GuidanceWorkspace", () => ({ default: function FakeGuidanceWorkspace() {
  const [draft, setDraft] = useState("");
  useEffect(() => {
    microphoneMounted();
    return () => microphoneReleased();
  }, []);
  return <><button>Start recording</button><input aria-label="Test chat draft" value={draft} onChange={(event) => setDraft(event.target.value)} /></>;
} }));

beforeEach(() => {
  state.user = null;
  state.checkingAuth = false;
  state.signupResult = null;
  state.accessOverride = null;
  state.mfaHints = [];
});
afterEach(() => cleanup());

it("shows recovery help without referring to an absent backup selector", () => {
  state.mfaHints = [{ uid: "main", displayName: "Main authenticator" }];
  render(<AuthPage />);
  fireEvent.click(screen.getByRole("button", { name: "Google sign in" }));
  fireEvent.click(screen.getByText("Lost access to your authenticator?"));
  expect(screen.queryByLabelText("Authenticator")).toBeNull();
  expect(screen.queryByText(/selector above/)).toBeNull();
  expect(screen.getByText(/contact the service owner/)).toBeTruthy();
});

it("explains and submits the selected backup authenticator when available", async () => {
  state.mfaHints = [{ uid: "main", displayName: "Main authenticator" }, { uid: "backup", displayName: "Backup authenticator" }];
  render(<AuthPage />);
  fireEvent.click(screen.getByRole("button", { name: "Google sign in" }));
  fireEvent.click(screen.getByText("Lost access to your authenticator?"));
  expect(screen.getByText(/Try another authenticator/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Authenticator"), { target: { value: "backup" } });
  fireEvent.change(screen.getByLabelText("Six-digit code"), { target: { value: "012345" } });
  fireEvent.click(screen.getByRole("button", { name: "Verify and log in" }));
  await screen.findByRole("button", { name: "Verify and log in" });
  expect(completeTotpSignIn).toHaveBeenCalledWith({ hints: state.mfaHints }, "012345", "backup");
});

it("shows only loading while backend access is being checked", () => {
  state.user = { uid: "one", emailVerified: true };
  state.accessOverride = { verified: false, checking: true, status: "checking" };
  render(<App />);
  expect(screen.getByRole("status", { name: "Loading" })).toBeTruthy();
  expect(screen.queryByRole("banner")).toBeNull();
  expect(screen.queryByRole("button", { name: "Start recording" })).toBeNull();
  expect(microphoneMounted).not.toHaveBeenCalled();
});

it("keeps the workspace hidden after a failed connection and offers retry", () => {
  const retry = vi.fn();
  state.user = { uid: "one", emailVerified: true };
  state.accessOverride = { verified: false, checking: false, status: "unavailable", retry };
  render(<App />);
  expect(screen.getByText("Unable to connect.")).toBeTruthy();
  expect(screen.queryByText("Verification required")).toBeNull();
  expect(screen.queryByRole("banner")).toBeNull();
  expect(microphoneMounted).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Retry connection" }));
  expect(retry).toHaveBeenCalledTimes(1);
});

// visitors see the voice entry point without mounting microphone resources.
it("opens login from the guest microphone action and returns home", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "Start with your voice." })).toBeTruthy();
  expect(microphoneMounted).not.toHaveBeenCalled();
  const guestMicrophone = screen.getByRole("button", { name: "Log in to use microphone" });
  expect(guestMicrophone.querySelector("svg")).not.toBeNull();
  fireEvent.click(guestMicrophone);
  expect(screen.getByText("Login form")).toBeTruthy();
  expect(microphoneMounted).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Back to home" }));
  expect(screen.getByRole("button", { name: "Sign up" })).toBeTruthy();
});

// different header actions must initialize the intended existing auth form.
it("opens signup and login with fresh form selection", () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  expect(screen.getByText("Signup form")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Back to home" }));
  fireEvent.click(screen.getByRole("button", { name: "Log in", exact: true }));
  expect(screen.getByText("Login form")).toBeTruthy();
});

// Account navigation keeps the workspace mounted; capture cleanup is tested separately.
it("preserves the workspace and draft across account navigation", () => {
  state.user = { uid: "caregiver", email: "caregiver@example.test", emailVerified: true };
  render(<App />);
  expect(screen.getAllByRole("button", { name: "Start recording" })).toHaveLength(1);
  fireEvent.change(screen.getByLabelText("Test chat draft"), { target: { value: "Unsent message" } });
  fireEvent.click(screen.getByRole("button", { name: "My Account" }));
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByText(/Account: caregiver@example.test/)).toBeTruthy();
  expect(microphoneReleased).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Start recording" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Back to home" }));
  expect(screen.getByRole("button", { name: "Start recording" })).toBeTruthy();
  expect(microphoneMounted).toHaveBeenCalledTimes(1);
  expect(screen.getByLabelText("Test chat draft").value).toBe("Unsent message");
});

// account changes replace the recording owner and logout restores the guest view.
it("cleans up on account replacement and logout", () => {
  state.user = { uid: "first", email: "first@example.test", emailVerified: true };
  const { rerender } = render(<App />);
  state.user = { uid: "second", email: "second@example.test", emailVerified: true };
  rerender(<App />);
  expect(microphoneReleased).toHaveBeenCalledTimes(1);
  state.user = null;
  rerender(<App />);
  expect(microphoneReleased).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: "Log in to use microphone" })).toBeTruthy();
});

it("clears the retained workspace after saved-data deletion", () => {
  state.user = { uid: "caregiver", emailVerified: true };
  render(<App />);
  fireEvent.change(screen.getByLabelText("Test chat draft"), { target: { value: "Private draft" } });
  fireEvent.click(screen.getByRole("button", { name: "My Account" }));
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.click(screen.getByRole("button", { name: "Simulate saved data deletion" }));
  fireEvent.click(screen.getByRole("button", { name: "Back to home" }));
  expect(screen.getByLabelText("Test chat draft").value).toBe("");
  expect(microphoneReleased).toHaveBeenCalledTimes(1);
});

// registration still reaches account onboarding rather than bypassing verification.
it("shows account onboarding after signup with the correct verification flag", () => {
  const { rerender } = render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  state.user = { uid: "new-user", email: "new@example.test", emailVerified: false };
  state.signupResult = { user: state.user, verificationEmailRequested: true };
  rerender(<App />);
  expect(screen.getByText(/Verification requested: true/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Start recording" })).toBeNull();
});

// firebase publishes the signed-in user after login, including a resolved mfa challenge.
it.each(["Log in", "Log in to use microphone", "Sign up"])(
  "opens the microphone automatically after verified authentication from %s",
  (entry) => {
    const { rerender } = render(<App />);
    fireEvent.click(screen.getByRole("button", { name: entry, exact: true }));
    expect(screen.queryByRole("button", { name: "Start recording" })).toBeNull();
    state.user = { uid: "verified", email: "verified@example.test", emailVerified: true };
    rerender(<App />);
    expect(screen.getByRole("heading", { name: "Start with your voice." })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start recording" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Back to home" })).toBeNull();

    // intentional account navigation must not be redirected back home.
    fireEvent.click(screen.getByRole("button", { name: "My Account" }));
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByText(/Account: verified@example.test/)).toBeTruthy();
  },
);

// an unsuccessful or unfinished login cannot mount microphone controls.
it("stays on login until a user is authenticated", () => {
  const { rerender } = render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Log in", exact: true }));
  rerender(<App />);
  expect(screen.getByText("Login form")).toBeTruthy();
  expect(microphoneMounted).not.toHaveBeenCalled();
});

// logout shows the public header, and a subsequent login still opens the microphone.
it("returns to the microphone after logout from account and subsequent login", () => {
  state.user = { uid: "first", email: "first@example.test", emailVerified: true };
  const { rerender } = render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "My Account" }));
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  state.user = null;
  rerender(<App />);
  const navigation = within(screen.getByRole("navigation", { name: "Account" }));
  expect(navigation.getByRole("button", { name: "Log in", exact: true })).toBeTruthy();
  expect(navigation.getByRole("button", { name: "Sign up" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Start with your voice." })).toBeTruthy();
  expect(screen.queryByText("Login form")).toBeNull();
  expect(screen.queryByRole("button", { name: "Back to home" })).toBeNull();
  fireEvent.click(navigation.getByRole("button", { name: "Log in", exact: true }));
  expect(screen.getByText("Login form")).toBeTruthy();
  state.user = { uid: "second", email: "second@example.test", emailVerified: true };
  rerender(<App />);
  expect(screen.getByRole("button", { name: "Start recording" })).toBeTruthy();
  expect(screen.queryByText(/Account: second@example.test/)).toBeNull();
});

// onboarding may be rendered on a login or signup screen, so logout must reset both.
it.each(["Log in", "Sign up"])("returns home after logout from unverified %s onboarding", (entry) => {
  const { rerender } = render(<App />);
  fireEvent.click(screen.getByRole("button", { name: entry, exact: true }));
  state.user = { uid: "unverified", email: "unverified@example.test", emailVerified: false };
  rerender(<App />);
  expect(screen.getByText(/Account: unverified@example.test/)).toBeTruthy();
  state.user = null;
  rerender(<App />);
  const navigation = within(screen.getByRole("navigation", { name: "Account" }));
  expect(navigation.getByRole("button", { name: "Log in", exact: true })).toBeTruthy();
  expect(navigation.getByRole("button", { name: "Sign up" })).toBeTruthy();
  expect(screen.queryByText("Login form")).toBeNull();
  expect(screen.queryByText("Signup form")).toBeNull();
  expect(microphoneMounted).not.toHaveBeenCalled();
});

// email-password sign-in does not hide required email verification onboarding.
it("keeps unverified login on the account setup screen", () => {
  const { rerender } = render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Log in", exact: true }));
  state.user = { uid: "unverified", email: "unverified@example.test", emailVerified: false };
  rerender(<App />);
  expect(screen.getByText(/Account: unverified@example.test/)).toBeTruthy();
  expect(microphoneMounted).not.toHaveBeenCalled();
});

// auth checking must not briefly mount the microphone or show a login form.
it("waits for authentication initialization", () => {
  state.checkingAuth = true;
  render(<App />);
  expect(screen.getByText("Checking sign-in...")).toBeTruthy();
  expect(microphoneMounted).not.toHaveBeenCalled();
});

// identity belongs to the shared header, not the microphone content area.
it("shows the name, verified badge and account action in the header across screens", () => {
  state.user = { uid: "verified", displayName: "Vinit", email: "vinit@example.test", emailVerified: true };
  render(<App />);
  const header = within(screen.getByRole("banner"));
  expect(header.getByText("Vinit")).toBeTruthy();
  expect(header.getByText("Verified")).toBeTruthy();
  expect(screen.queryByText(/Voice transcription requires/)).toBeNull();
  fireEvent.click(header.getByRole("button", { name: "My Account" }));
  fireEvent.click(header.getByRole("button", { name: "Settings" }));
  expect(within(screen.getByRole("banner")).getByText("Vinit")).toBeTruthy();
  fireEvent.click(header.getByRole("button", { name: "Parenting Voice Assistant" }));
  expect(screen.getByRole("button", { name: "Start recording" })).toBeTruthy();
});
