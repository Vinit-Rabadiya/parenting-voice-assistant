import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useState } from "react";
import { readChildSelection, saveChildSelection } from "../../frontend/src/services/childSelection";
import ChildProfiles from "../../frontend/src/components/ChildProfiles";
import { createChild, deleteChild, listChildren, updateChild } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({
  createChild: vi.fn(), deleteChild: vi.fn(), listChildren: vi.fn(), updateChild: vi.fn(),
}));

const child = { id: "child-1", name: "Example", date_of_birth: "2026-04-21", age_label: "6 months",
  milestones: ["Responds to familiar voices"], baseline_milestones: ["Babbles"] };
const otherChild = { ...child, id: "child-2", name: "Another child" };
const emptyHealthDetails = { allergies: "", conditions: "", history: "", care_instructions: "", test_result_notes: "" };
const originalDialogMethods = Object.fromEntries(["showModal", "close"].map((name) => [
  name, Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name),
]));

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
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

it("waits for the authenticated profile list when no child is selected", async () => {
  let finish;
  listChildren.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  const onSelect = vi.fn();
  render(<ChildProfiles userId="account-one" selectedChild={null} onSelect={onSelect} />);
  expect(screen.getByRole("status", { name: "Loading chat" })).toBeTruthy();
  expect(onSelect).not.toHaveBeenCalled();
  await act(async () => { finish([child]); });
  expect(onSelect).toHaveBeenCalledWith(child);
  expect(screen.queryByRole("status", { name: "Loading chat" })).toBeNull();
});

it("keeps an already selected child's chat visible during a profile refresh", async () => {
  let finish;
  listChildren.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  render(<ChildProfiles userId="account-one" selectedChild={child} onSelect={vi.fn()} />);
  expect(listChildren).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("status", { name: "Loading chat" })).toBeNull();
  // Editing and selection still wait for fresh data; the rest of the chat does not.
  expect(screen.getByRole("button", { name: /Example/ }).disabled).toBe(true);
  await act(async () => { finish([child, otherChild]); });
  expect(screen.getByRole("button", { name: /Example/ }).disabled).toBe(false);
});

it("reconciles a deleted selected child when refreshed profiles arrive", async () => {
  let finish;
  listChildren.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  function Workspace() {
    const [selected, select] = useState(child);
    return <ChildProfiles userId="account-one" selectedChild={selected} onSelect={select} />;
  }
  render(<Workspace />);
  expect(screen.queryByRole("status", { name: "Loading chat" })).toBeNull();
  await act(async () => { finish([otherChild]); });
  expect(screen.getByRole("button", { name: /Another child/ }).disabled).toBe(false);
  expect(screen.queryByRole("button", { name: /Example/ })).toBeNull();
  expect(readChildSelection("account-one")).toBe(otherChild.id);
});

it("uses owned startup profiles without fetching them again and updates the parent after deletion", async () => {
  const onSelect = vi.fn(), onProfilesChange = vi.fn();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  deleteChild.mockResolvedValue(undefined);
  render(<ChildProfiles userId="account-one" selectedChild={child} onSelect={onSelect}
    initialChildren={[child, otherChild]} onProfilesChange={onProfilesChange} />);
  await openPicker();
  expect(listChildren).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "View child details" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete child profile" }));
  await waitFor(() => expect(onProfilesChange).toHaveBeenLastCalledWith([otherChild]));
  expect(onSelect).toHaveBeenLastCalledWith(otherChild);
});

it("keeps edited profiles current across cached selector remounts", async () => {
  const edited = { ...child, name: "Updated child" };
  updateChild.mockResolvedValue(edited);
  function Workspace() {
    const [selected, select] = useState(child);
    const [profiles, remember] = useState([child, otherChild]);
    return <ChildProfiles key={selected.id} selectedChild={selected} onSelect={select}
      initialChildren={profiles} onProfilesChange={remember} />;
  }
  render(<Workspace />);
  await openPicker();
  fireEvent.click(screen.getByRole("button", { name: "Edit child profile" }));
  fireEvent.change(screen.getByLabelText("Child name"), { target: { value: edited.name } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByRole("button", { name: /Updated child/ });
  fireEvent.click(screen.getByRole("button", { name: /Updated child/ }));
  fireEvent.click(screen.getByRole("button", { name: /Another child/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Another child/ }));
  expect(await screen.findByRole("button", { name: /Updated child/ })).toBeTruthy();
  expect(screen.queryByRole("button", { name: /^Example/ })).toBeNull();
  expect(listChildren).not.toHaveBeenCalled();
});

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
  const birthDate = within(dialog).getByLabelText("Date of birth");
  expect(document.getElementById(birthDate.getAttribute("aria-describedby")).textContent)
    .toContain("birth through the second birthday (0–24 months)");
  fireEvent.change(birthDate, { target: { value: "2026-04-21" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save child" }));
  await waitFor(() => expect(createChild).toHaveBeenCalledWith({ name: "New child", date_of_birth: "2026-04-21", milestones: [],
    health_details: emptyHealthDetails, use_health_details: false }));
  await waitFor(() => expect(onSelect).toHaveBeenCalledWith(created));
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("retains a newly created profile when the empty workspace becomes a chat", async () => {
  createChild.mockResolvedValue(child);
  function StartupProfiles() {
    const [profiles, setProfiles] = useState([]);
    const [selected, setSelected] = useState(null);
    return <ChildProfiles key={selected ? "chat" : "onboarding"} userId="startup-owner"
      selectedChild={selected} onSelect={setSelected} initialChildren={profiles} onProfilesChange={setProfiles} />;
  }
  render(<StartupProfiles />);
  const trigger = await screen.findByRole("button", { name: /Choose child profile/ });
  await waitFor(() => expect(trigger.disabled).toBe(false));
  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole("button", { name: /Add child/ }));
  const dialog = screen.getByRole("dialog", { name: "Add child" });
  fireEvent.change(within(dialog).getByLabelText("Child name"), { target: { value: child.name } });
  fireEvent.change(within(dialog).getByLabelText("Date of birth"), { target: { value: child.date_of_birth } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save child" }));
  await screen.findByRole("button", { name: /Example/ });
  expect(listChildren).not.toHaveBeenCalled();
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
    health_details: emptyHealthDetails, use_health_details: false,
  }));
});

it("saves health notes privately when using them in replies is unavailable", async () => {
  updateChild.mockResolvedValue(child);
  render(<ChildProfiles selectedChild={child} onSelect={vi.fn()} />);
  await openPicker();
  fireEvent.click(screen.getByRole("button", { name: "Edit child profile" }));
  fireEvent.click(screen.getByText("Health and care details (optional)"));
  fireEvent.change(screen.getByLabelText("Known allergies"), { target: { value: "Example note" } });
  expect(screen.getByLabelText("Use health details to tailor replies").disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(updateChild).toHaveBeenCalledWith(child.id, expect.objectContaining({
    health_details: { ...emptyHealthDetails, allergies: "Example note" }, use_health_details: false,
  })));
});

it("keeps existing notes and requires a separate choice before using them in replies", async () => {
  const available = { ...child, health_context_available: true, health_details: { history: "Saved note" } };
  updateChild.mockResolvedValue(available);
  listChildren.mockResolvedValue([available]);
  render(<ChildProfiles selectedChild={available} onSelect={vi.fn()} />);
  await openPicker();
  fireEvent.click(screen.getByRole("button", { name: "Edit child profile" }));
  expect(screen.getByLabelText("Relevant health history").value).toBe("Saved note");
  const choice = screen.getByLabelText("Use health details to tailor replies");
  expect(choice.checked).toBe(false);
  expect(choice.disabled).toBe(false);
  fireEvent.click(choice);
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(updateChild).toHaveBeenCalledWith(child.id, expect.objectContaining({
    health_details: { ...emptyHealthDetails, history: "Saved note" }, use_health_details: true,
  })));
});

it("can clear saved health notes without deleting the child", async () => {
  const saved = { ...child, health_details: { conditions: "An existing note" } };
  listChildren.mockResolvedValue([saved]);
  updateChild.mockResolvedValue({ ...child, health_details: emptyHealthDetails });
  render(<ChildProfiles selectedChild={saved} onSelect={vi.fn()} />);
  await openPicker();
  fireEvent.click(screen.getByRole("button", { name: "Edit child profile" }));
  fireEvent.change(screen.getByLabelText("Diagnosed conditions"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(updateChild).toHaveBeenCalledWith(child.id, expect.objectContaining({ health_details: emptyHealthDetails })));
  expect(deleteChild).not.toHaveBeenCalled();
});

it("preserves health-note drafts after a failed save and displays notes only in profile details", async () => {
  updateChild.mockRejectedValue(new Error("Profile could not be saved."));
  render(<ChildProfiles selectedChild={child} onSelect={vi.fn()} />);
  await openPicker();
  expect(screen.queryByLabelText("Known allergies")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Edit child profile" }));
  fireEvent.change(screen.getByLabelText("Known allergies"), { target: { value: "Unsaved health note" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByText("Profile could not be saved.");
  expect(screen.getByLabelText("Known allergies").value).toBe("Unsaved health note");
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

function SelectionHarness({ userId = "account-a" }) {
  const [selected, setSelected] = useState(null);
  return <ChildProfiles userId={userId} selectedChild={selected} onSelect={setSelected} />;
}

it("restores the last chosen profile after remounting from the authenticated list", async () => {
  const view = render(<SelectionHarness />);
  await openPicker();
  fireEvent.click(screen.getByRole("button", { name: /Another child/ }));
  expect(readChildSelection("account-a")).toBe(otherChild.id);
  view.unmount();
  render(<SelectionHarness />);
  expect(await screen.findByRole("button", { name: /Another child/ })).toBeTruthy();
});

it("does not restore another account's profile or trust an unknown stored ID", async () => {
  saveChildSelection("account-a", otherChild.id);
  saveChildSelection("account-b", "deleted-or-foreign-child");
  render(<SelectionHarness userId="account-b" />);
  expect(await screen.findByRole("button", { name: /Example/ })).toBeTruthy();
  expect(readChildSelection("account-b")).toBe(child.id);
  expect(readChildSelection("account-a")).toBe(otherChild.id);
});

it("clears a stale selection when the account has no children", async () => {
  saveChildSelection("account-a", child.id);
  listChildren.mockResolvedValue([]);
  render(<SelectionHarness />);
  await screen.findByRole("button", { name: /Choose child profile/ });
  expect(readChildSelection("account-a")).toBeNull();
});

it("updates the remembered selection after deleting the selected child", async () => {
  saveChildSelection("account-a", child.id);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  deleteChild.mockResolvedValue(undefined);
  render(<SelectionHarness />);
  await openPicker();
  fireEvent.click(screen.getByRole("button", { name: "View child details" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete child profile" }));
  await waitFor(() => expect(readChildSelection("account-a")).toBe(otherChild.id));
});

it("keeps profiles usable when browser storage is blocked", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("Blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Blocked"); });
  render(<SelectionHarness />);
  await openPicker();
  fireEvent.click(screen.getByRole("button", { name: /Another child/ }));
  expect(screen.getByRole("button", { name: /Another child/ })).toBeTruthy();
});
