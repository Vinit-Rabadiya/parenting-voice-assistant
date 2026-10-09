import { useEffect } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "../../frontend/src/App";

const { state, microphoneMounted, microphoneReleased } = vi.hoisted(() => ({
  state: { user: null, checkingAuth: false, signupResult: null, setSignupResult: vi.fn() },
  microphoneMounted: vi.fn(), microphoneReleased: vi.fn(),
}));

// keep real page navigation and auth form selection, replacing external services.
vi.mock("../../frontend/src/context/AuthProvider", () => ({ AuthProvider: ({ children }) => children }));
vi.mock("../../frontend/src/hooks/useAuth", () => ({ useAuth: () => state }));
vi.mock("../../frontend/src/services/auth", () => ({ completeTotpSignIn: vi.fn() }));
vi.mock("../../frontend/src/components/LoginForm", () => ({ default: () => <div>Login form</div> }));
vi.mock("../../frontend/src/components/SignUpForm", () => ({ default: () => <div>Signup form</div> }));
vi.mock("../../frontend/src/components/GoogleSignInButton", () => ({ default: () => <button>Google sign in</button> }));
vi.mock("../../frontend/src/pages/AccountPage", () => ({ default: ({ email, verificationEmailRequested }) => (
  <div>Account: {email}. Verification requested: {String(verificationEmailRequested)}</div>
) }));
vi.mock("../../frontend/src/components/MicrophoneControls", () => ({ default: function FakeMicrophone() {
  useEffect(() => {
    microphoneMounted();
    return () => microphoneReleased();
  }, []);
  return <button>Start recording</button>;
} }));

beforeEach(() => {
  state.user = null;
  state.checkingAuth = false;
  state.signupResult = null;
});
afterEach(() => cleanup());

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

// leaving the signed-in voice view unmounts recording and triggers its cleanup.
it("navigates to account and back without duplicate microphone instances", () => {
  state.user = { uid: "caregiver", email: "caregiver@example.test" };
  render(<App />);
  expect(screen.getAllByRole("button", { name: "Start recording" })).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "My Account" }));
  expect(screen.getByText(/Account: caregiver@example.test/)).toBeTruthy();
  expect(microphoneReleased).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Back to home" }));
  expect(screen.getByRole("button", { name: "Start recording" })).toBeTruthy();
  expect(microphoneMounted).toHaveBeenCalledTimes(2);
});

// account changes replace the recording owner and logout restores the guest view.
it("cleans up on account replacement and logout", () => {
  state.user = { uid: "first", email: "first@example.test" };
  const { rerender } = render(<App />);
  state.user = { uid: "second", email: "second@example.test" };
  rerender(<App />);
  expect(microphoneReleased).toHaveBeenCalledTimes(1);
  state.user = null;
  rerender(<App />);
  expect(microphoneReleased).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: "Log in to use microphone" })).toBeTruthy();
});

// registration still reaches account onboarding rather than bypassing verification.
it("shows account onboarding after signup with the correct verification flag", () => {
  const { rerender } = render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  state.user = { uid: "new-user", email: "new@example.test" };
  state.signupResult = { user: state.user, verificationEmailRequested: true };
  rerender(<App />);
  expect(screen.getByText(/Verification requested: true/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Start recording" })).toBeNull();
});

// auth checking must not briefly mount the microphone or show a login form.
it("waits for authentication initialization", () => {
  state.checkingAuth = true;
  render(<App />);
  expect(screen.getByText("Checking sign-in...")).toBeTruthy();
  expect(microphoneMounted).not.toHaveBeenCalled();
});
