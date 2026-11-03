import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import PrivacyConsent from "../../frontend/src/components/PrivacyConsent";
import { acceptPrivacyConsent, getPrivacyConsent } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({
  getPrivacyConsent: vi.fn(), acceptPrivacyConsent: vi.fn(),
}));
const notice = { version: "test-v1", accepted: false, notice: ["Information about processing."] };
const workspace = (allowed) => <p>{allowed ? "Coaching workspace" : "Read-only history"}</p>;
beforeEach(() => {
  vi.resetAllMocks();
  getPrivacyConsent.mockResolvedValue(notice);
});
afterEach(() => cleanup());

it("uses the verified bootstrap notice once and invalidates it after a server challenge", async () => {
  const renderWorkspace = vi.fn(workspace);
  render(<PrivacyConsent initialNotice={{ ...notice, accepted: true }}>{renderWorkspace}</PrivacyConsent>);
  expect(screen.getByText("Coaching workspace")).toBeTruthy();
  expect(getPrivacyConsent).not.toHaveBeenCalled();
  expect(renderWorkspace).toHaveBeenLastCalledWith(true, true);
  act(() => window.dispatchEvent(new Event("privacy-consent-required")));
  await screen.findByText("Information about processing.");
  expect(screen.queryByText("Coaching workspace")).toBeNull();
  expect(getPrivacyConsent).toHaveBeenCalledTimes(1);
  acceptPrivacyConsent.mockResolvedValue({ ...notice, accepted: true });
  screen.getAllByRole("checkbox").forEach(input => fireEvent.click(input));
  fireEvent.click(screen.getByRole("button", { name: "Accept and continue" }));
  await screen.findByText("Coaching workspace");
  expect(renderWorkspace).toHaveBeenLastCalledWith(true, false);
});

it("requires both unchecked confirmations before recording consent", async () => {
  acceptPrivacyConsent.mockResolvedValue({ ...notice, accepted: true });
  render(<PrivacyConsent>{workspace}</PrivacyConsent>);
  await screen.findByText("Information about processing.");
  expect(screen.queryByText("Coaching workspace")).toBeNull();
  const checkboxes = screen.getAllByRole("checkbox");
  expect(checkboxes.every((input) => !input.checked)).toBe(true);
  const accept = screen.getByRole("button", { name: "Accept and continue" });
  expect(accept.disabled).toBe(true);
  fireEvent.click(checkboxes[0]);
  expect(accept.disabled).toBe(true);
  fireEvent.click(checkboxes[1]);
  fireEvent.click(accept);
  await screen.findByText("Coaching workspace");
  expect(acceptPrivacyConsent).toHaveBeenCalledWith("test-v1", expect.any(AbortSignal));
});

it("opens existing data read-only without accepting", async () => {
  render(<PrivacyConsent>{workspace}</PrivacyConsent>);
  await screen.findByText("Information about processing.");
  fireEvent.click(screen.getByRole("button", { name: "View or delete existing data without accepting" }));
  await screen.findByText("Read-only history");
  expect(screen.queryByText("Coaching workspace")).toBeNull();
  expect(acceptPrivacyConsent).not.toHaveBeenCalled();
});

it("shows only a loading screen until accepted consent is confirmed", async () => {
  let finish;
  getPrivacyConsent.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  render(<PrivacyConsent>{workspace}</PrivacyConsent>);
  expect(screen.getByRole("status", { name: "Loading chat" })).toBeTruthy();
  expect(screen.queryByText("Privacy and consent")).toBeNull();
  finish({ ...notice, accepted: true });
  await screen.findByText("Coaching workspace");
  expect(screen.queryByRole("status", { name: "Loading chat" })).toBeNull();
  expect(getPrivacyConsent).toHaveBeenCalledTimes(1);
});

it("loads the workspace directly only for current accepted consent", async () => {
  getPrivacyConsent.mockResolvedValue({ ...notice, accepted: true });
  render(<PrivacyConsent>{workspace}</PrivacyConsent>);
  await screen.findByText("Coaching workspace");
  expect(acceptPrivacyConsent).not.toHaveBeenCalled();
});

it("does not unlock coaching if consent storage fails", async () => {
  acceptPrivacyConsent.mockRejectedValue(new Error("Consent could not be saved."));
  render(<PrivacyConsent>{workspace}</PrivacyConsent>);
  await screen.findByText("Information about processing.");
  screen.getAllByRole("checkbox").forEach((input) => fireEvent.click(input));
  fireEvent.click(screen.getByRole("button", { name: "Accept and continue" }));
  await screen.findByRole("alert");
  expect(screen.queryByText("Coaching workspace")).toBeNull();
});

it("reloads a changed notice with confirmations cleared", async () => {
  render(<PrivacyConsent>{workspace}</PrivacyConsent>);
  await screen.findByText("Information about processing.");
  screen.getAllByRole("checkbox").forEach((input) => fireEvent.click(input));
  getPrivacyConsent.mockResolvedValue({ ...notice, version: "test-v2" });
  fireEvent.click(screen.getByRole("button", { name: "Reload notice" }));
  await screen.findByText("Notice version: test-v2");
  expect(screen.getAllByRole("checkbox").every((input) => !input.checked)).toBe(true);
});

it("does not trust a malformed accepted response", async () => {
  getPrivacyConsent.mockResolvedValue({ accepted: true });
  render(<PrivacyConsent>{workspace}</PrivacyConsent>);
  await screen.findByRole("alert");
  expect(screen.queryByText("Coaching workspace")).toBeNull();
});

it("reloads accepted consent only when the server explicitly requires it again", async () => {
  getPrivacyConsent.mockResolvedValueOnce({ ...notice, accepted: true })
    .mockResolvedValueOnce({ ...notice, version: "test-v2" });
  render(<PrivacyConsent>{workspace}</PrivacyConsent>);
  await screen.findByText("Coaching workspace");
  fireEvent(window, new Event("privacy-consent-required"));
  await screen.findByText("Notice version: test-v2");
  expect(screen.queryByText("Coaching workspace")).toBeNull();
  expect(getPrivacyConsent).toHaveBeenCalledTimes(2);
});

it("aborts an in-flight notice request when the account workspace unmounts", async () => {
  getPrivacyConsent.mockReturnValue(new Promise(() => {}));
  const view = render(<PrivacyConsent>{workspace}</PrivacyConsent>);
  await waitFor(() => expect(getPrivacyConsent).toHaveBeenCalledTimes(1));
  const signal = getPrivacyConsent.mock.calls[0][0];
  view.unmount();
  expect(signal.aborted).toBe(true);
});
