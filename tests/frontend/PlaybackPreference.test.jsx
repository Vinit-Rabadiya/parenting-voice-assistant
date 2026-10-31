import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import usePlaybackPreference, { clearPlaybackPreference } from "../../frontend/src/hooks/usePlaybackPreference";

beforeEach(() => localStorage.clear());
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("persists the choice across remounts without applying it to another account", () => {
  const first = renderHook(() => usePlaybackPreference("first-account"));
  expect(first.result.current.automatic).toBe(true);
  act(() => expect(first.result.current.setAutomatic(false)).toBe(true));
  first.unmount();
  const restored = renderHook(() => usePlaybackPreference("first-account"));
  const other = renderHook(() => usePlaybackPreference("other-account"));
  expect(restored.result.current.automatic).toBe(false);
  expect(other.result.current.automatic).toBe(true);
  act(() => clearPlaybackPreference("first-account"));
  expect(restored.result.current.automatic).toBe(true);
  expect(localStorage.length).toBe(0);
});

it("updates mounted readers in the same tab and handles changes from another tab", () => {
  const first = renderHook(() => usePlaybackPreference("shared-account"));
  const second = renderHook(() => usePlaybackPreference("shared-account"));
  act(() => first.result.current.setAutomatic(false));
  expect(second.result.current.automatic).toBe(false);
  const key = localStorage.key(0);
  act(() => {
    localStorage.setItem(key, "true");
    window.dispatchEvent(new StorageEvent("storage", { key, newValue: "true" }));
  });
  expect(second.result.current.automatic).toBe(true);
  act(() => {
    localStorage.setItem(key, "invalid");
    window.dispatchEvent(new StorageEvent("storage", { key, newValue: "invalid" }));
  });
  expect(second.result.current.automatic).toBe(false);
});

it("keeps audio off when storage cannot be read and still applies explicit tab choices", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("Storage blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Storage blocked"); });
  const view = renderHook(() => usePlaybackPreference("restricted-account"));
  expect(view.result.current.automatic).toBe(false);
  act(() => expect(view.result.current.setAutomatic(true)).toBe(false));
  expect(view.result.current.automatic).toBe(true);
  view.unmount();
  expect(renderHook(() => usePlaybackPreference("restricted-account")).result.current.automatic).toBe(true);
  expect(renderHook(() => usePlaybackPreference("another-restricted-account")).result.current.automatic).toBe(false);
  act(() => clearPlaybackPreference("restricted-account"));
});
