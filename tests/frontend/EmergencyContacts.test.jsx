import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import EmergencyContacts from "../../frontend/src/components/EmergencyContacts";
import contacts from "../../shared/kenya-contacts.json";
import { stopGuidanceAudio } from "../../frontend/src/hooks/useGuidanceAudio";

vi.mock("../../frontend/src/hooks/useGuidanceAudio", () => ({ stopGuidanceAudio: vi.fn() }));
const originalMethods = Object.fromEntries(["showModal", "close"].map((name) =>
  [name, Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name)]));

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true, value: function () { this.open = true; },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true, value: function () { this.open = false; },
  });
});
afterEach(() => {
  cleanup();
  for (const [name, descriptor] of Object.entries(originalMethods)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else delete HTMLDialogElement.prototype[name];
  }
});

it("opens every shared contact as a phone link without a network request", () => {
  const onOpenChange = vi.fn();
  const fetch = vi.spyOn(globalThis, "fetch");
  render(<EmergencyContacts onOpenChange={onOpenChange} />);
  expect(screen.queryByRole("dialog")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Emergency" }));
  const dialog = screen.getByRole("dialog", { name: "Emergency contacts — Kenya" });
  const phoneLinks = within(dialog).getAllByRole("link").filter((link) => link.getAttribute("href").startsWith("tel:"));
  expect(phoneLinks.map((link) => link.getAttribute("href"))).toEqual(contacts.map((contact) => contact.url));
  expect(within(dialog).getByRole("region", { name: "Hospital contacts" })).toBeTruthy();
  expect(within(dialog).getByText("Nairobi")).toBeTruthy();
  expect(stopGuidanceAudio).toHaveBeenCalledOnce();
  expect(onOpenChange).toHaveBeenLastCalledWith(true);
  expect(fetch).not.toHaveBeenCalled();
  fetch.mockRestore();
});

it("closes with Escape cancellation and restores focus and background scrolling", () => {
  const onOpenChange = vi.fn();
  document.body.style.overflow = "auto";
  render(<EmergencyContacts onOpenChange={onOpenChange} />);
  const trigger = screen.getByRole("button", { name: "Emergency" });
  trigger.focus();
  fireEvent.click(trigger);
  expect(document.body.style.overflow).toBe("hidden");
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Close" }));
  fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.body.style.overflow).toBe("auto");
  expect(document.activeElement).toBe(trigger);
  expect(onOpenChange).toHaveBeenLastCalledWith(false);
  document.body.style.overflow = "";
});

it("supports the close button and releases the dialog when unmounted", () => {
  const onOpenChange = vi.fn();
  const view = render(<EmergencyContacts onOpenChange={onOpenChange} />);
  fireEvent.click(screen.getByRole("button", { name: "Emergency" }));
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Emergency" }));
  view.unmount();
  expect(document.body.style.overflow).toBe("");
  expect(onOpenChange).toHaveBeenLastCalledWith(false);
});
