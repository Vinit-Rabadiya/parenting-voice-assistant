import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ChildProfiles from "../../frontend/src/components/ChildProfiles";
import { createChild, deleteChild, listChildren, updateChild } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({
  createChild: vi.fn(), deleteChild: vi.fn(), listChildren: vi.fn(), updateChild: vi.fn(),
}));

const child = { id: "child-1", name: "Example", date_of_birth: "2026-04-21", age_label: "6 months",
  milestones: ["Responds to familiar voices"], baseline_milestones: ["Babbles"] };
const otherChild = { ...child, id: "child-2", name: "Another child" };
const originalDialogMethods = Object.fromEntries(["showModal", "close"].map((name) => [
  name, Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name),
]));

beforeEach(() => {
  vi.resetAllMocks();
  listChildren.mockResolvedValue([child, otherChild]);
  // jsdom does not implement native dialog focus trapping or its modal methods.
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true, value: vi.fn(function () { this.setAttribute("open", ""); }),
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true, value: vi.fn(function () { this.removeAttribute("open"); }),
  });
});
afterEach(() => {
  cleanup(); vi.restoreAllMocks();
  for (const [name, descriptor] of Object.entries(originalDialogMethods)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else delete HTMLDialogElement.prototype[name];
  }
});

async function openPicker() {
  const trigger = await screen.findByRole("button", { name: /Example/ });
  await waitFor(() => expect(trigger.disabled).toBe(false));
  fireEvent.click(trigger);
  return trigger;
}

it("allows viewing and deleting a profile while changes require consent", async () => {
  const onSelect = vi.fn();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  deleteChild.mockResolvedValue(undefined);
  render(<ChildProfiles selectedChild={child} onSelect={onSelect} allowChanges={false} />);
  await openPicker();
  expect(screen.queryByRole("button", { name: /Add child/ })).toBeNull();
  expect(screen.queryByRole("button", { name: "Edit child profile" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "View child details" }));
  expect(screen.queryByRole("button", { name: "Edit child profile" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Delete child profile" }));
  await waitFor(() => expect(deleteChild).toHaveBeenCalledWith(child.id));
  expect(createChild).not.toHaveBeenCalled();
  expect(updateChild).not.toHaveBeenCalled();
});

it("switches children from a floating picker without opening a form", async () => {
  const onSelect = vi.fn();
  render(<ChildProfiles selectedChild={child} onSelect={onSelect} />);
  const trigger = await openPicker();
  fireEvent.click(screen.getByRole("button", { name: /Another child/ }));
  expect(onSelect).toHaveBeenCalledWith(otherChild);
  expect(trigger.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByRole("textbox")).toBeNull();
});

it("adds a child through a dialog with optional milestones", async () => {
  const onSelect = vi.fn();
  const created = { ...otherChild, name: "New child", milestones: [] };
  createChild.mockResolvedValue(created);
  render(<ChildProfiles selectedChild={child} onSelect={onSelect} />);
  await openPicker();
  fireEvent.click(screen.getByRole("button", { name: /Add child/ }));
  const dialog = screen.getByRole("dialog", { name: "Add child" });
  fireEvent.change(within(dialog).getByLabelText("Child name"), { target: { value: "New child" } });
  fireEvent.change(within(dialog).getByLabelText("Date of birth"), { target: { value: "2026-04-21" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save child" }));
  await waitFor(() => expect(createChild).toHaveBeenCalledWith({ name: "New child", date_of_birth: "2026-04-21", milestones: [] }));
  await waitFor(() => expect(onSelect).toHaveBeenCalledWith(created));
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("prefills the edit dialog and keeps existing milestones", async () => {
  const onSelect = vi.fn();
  updateChild.mockResolvedValue({ ...child, name: "Updated name" });
  render(<ChildProfiles selectedChild={child} onSelect={onSelect} />);
  await openPicker();
  fireEvent.click(screen.getByRole("button", { name: "Edit child profile" }));
  const dialog = screen.getByRole("dialog", { name: "Edit child profile" });
  expect(within(dialog).getByLabelText("Child name").value).toBe("Example");
  expect(within(dialog).getByLabelText("Milestone 1").value).toBe("Responds to familiar voices");
  fireEvent.change(within(dialog).getByLabelText("Child name"), { target: { value: "Updated name" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(updateChild).toHaveBeenCalledWith("child-1", {
    name: "Updated name", date_of_birth: "2026-04-21", milestones: ["Responds to familiar voices"],
  }));
});

it("cancels editing without saving and restores focus", async () => {
  render(<ChildProfiles selectedChild={child} onSelect={vi.fn()} />);
  const trigger = await openPicker();
  fireEvent.click(screen.getByRole("button", { name: "Edit child profile" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(updateChild).not.toHaveBeenCalled();
  expect(document.activeElement).toBe(trigger);
});

it("preserves the draft and error when saving fails", async () => {
  updateChild.mockRejectedValue(new Error("Profile could not be saved."));
  render(<ChildProfiles selectedChild={child} onSelect={vi.fn()} />);
  await openPicker();
  fireEvent.click(screen.getByRole("button", { name: "Edit child profile" }));
  fireEvent.change(screen.getByLabelText("Child name"), { target: { value: "Unsaved name" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByText("Profile could not be saved.");
  expect(screen.getByLabelText("Child name").value).toBe("Unsaved name");
  expect(screen.getByRole("dialog", { name: "Edit child profile" })).toBeTruthy();
});

it("still requires confirmation before deleting a profile", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<ChildProfiles selectedChild={child} onSelect={vi.fn()} />);
  await openPicker();
  fireEvent.click(screen.getByRole("button", { name: "View child details" }));
  expect(screen.getByText("Babbles")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Delete child profile" }));
  expect(deleteChild).not.toHaveBeenCalled();
});
