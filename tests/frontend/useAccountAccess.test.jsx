import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import useAccountAccess from "../../frontend/src/hooks/useAccountAccess";
import { getCurrentAccount } from "../../frontend/src/services/api";

vi.mock("../../frontend/src/services/api", () => ({ getCurrentAccount: vi.fn() }));
beforeEach(() => { getCurrentAccount.mockReset(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

// email verification alone is not enough to claim the backend accepted mfa.
it("checks automatically and marks verified only after server approval", async () => {
  let approve;
  getCurrentAccount.mockReturnValue(new Promise((resolve) => { approve = resolve; }));
  const user = { uid: "one", emailVerified: true };
  const { result } = renderHook(() => useAccountAccess(user));
  expect(result.current.checking).toBe(true);
  expect(result.current.verified).toBe(false);
  await act(async () => { approve({ uid: "one" }); });
  expect(result.current.verified).toBe(true);
});

it("reports rejected access and retries automatically when returning to the window", async () => {
  getCurrentAccount.mockRejectedValueOnce(new Error("Complete authenticator login first."))
    .mockResolvedValueOnce({ uid: "one" });
  const user = { uid: "one" };
  const { result } = renderHook(() => useAccountAccess(user));
  await waitFor(() => expect(result.current.error).toContain("authenticator"));
  expect(result.current.verified).toBe(false);
  await act(async () => { window.dispatchEvent(new Event("focus")); });
  expect(result.current.verified).toBe(true);
});

it("clears verification on logout and ignores a late response", async () => {
  let approve;
  getCurrentAccount.mockReturnValue(new Promise((resolve) => { approve = resolve; }));
  const { result, rerender } = renderHook(({ user }) => useAccountAccess(user), {
    initialProps: { user: { uid: "one" } },
  });
  const signal = getCurrentAccount.mock.calls[0][0];
  rerender({ user: null });
  expect(signal.aborted).toBe(true);
  await act(async () => { approve({ uid: "one" }); });
  expect(result.current).toEqual({ verified: false, checking: false, error: "" });
});

it("does not check signed-out visitors", () => {
  renderHook(() => useAccountAccess(null));
  expect(getCurrentAccount).not.toHaveBeenCalled();
});

it("times out even if the pending operation ignores cancellation", async () => {
  vi.useFakeTimers();
  let approve;
  getCurrentAccount.mockReturnValue(new Promise((resolve) => { approve = resolve; }));
  const user = { uid: "one" };
  const { result } = renderHook(() => useAccountAccess(user));
  await act(async () => { vi.advanceTimersByTime(15000); });
  expect(result.current.checking).toBe(false);
  expect(result.current.error).toContain("Could not verify");
  await act(async () => { approve({ uid: "one" }); });
  expect(result.current.verified).toBe(false);
});
