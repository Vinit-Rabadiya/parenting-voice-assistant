import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useState } from "react";
import GuidanceAnswer from "../../frontend/src/components/GuidanceAnswer";
import { getCurrentAccount } from "../../frontend/src/services/api";
import { auth } from "../../frontend/src/services/firebase";

const { renderText } = vi.hoisted(() => ({ renderText: vi.fn() }));
vi.mock("../../frontend/src/services/firebase", () => ({ auth: { currentUser: null } }));
vi.mock("../../frontend/src/components/GuidanceText", () => ({ default: ({ text }) => {
  renderText();
  return <p>{text}</p>;
} }));

const notice = { version: "test-notice", accepted: true, notice: ["Processing notice"] };
beforeEach(() => {
  vi.clearAllMocks();
  auth.currentUser = { uid: "account", getIdToken: async () => "token" };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("keeps 50 saved answers out of 20 draft renders but updates a changed answer", () => {
  const saved = Array.from({ length: 50 }, (_, index) => ({ id: `a${index}`, text: `Answer ${index}`, status: "answered" }));
  function Thread() {
    const [draft, setDraft] = useState("");
    const [messages, setMessages] = useState(saved);
    return <><input aria-label="Draft" value={draft} onChange={event => setDraft(event.target.value)} />
      <button onClick={() => setMessages(items => items.map((item, index) => index === 0 ? { ...item, text: "Updated answer" } : item))}>Update answer</button>
      {messages.map(message => <GuidanceAnswer key={message.id} message={message} automaticPlayback={false} />)}</>;
  }
  render(<Thread />);
  expect(renderText).toHaveBeenCalledTimes(50);
  const input = screen.getByLabelText("Draft");
  for (let index = 0; index < 20; index++) {
    fireEvent.change(input, { target: { value: `Draft ${index}` } });
  }
  expect(renderText).toHaveBeenCalledTimes(50);
  fireEvent.click(screen.getByText("Update answer"));
  expect(screen.getByText("Updated answer")).toBeTruthy();
  expect(renderText).toHaveBeenCalledTimes(51);
});

it("retrieves verified startup data in one non-cacheable authenticated request", async () => {
  const body = { uid: "account", role: "caregiver", consent: notice, children: [{ id: "child" }] };
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => body });
  vi.stubGlobal("fetch", fetch);
  await expect(getCurrentAccount()).resolves.toEqual(body);
  expect(fetch).toHaveBeenCalledExactlyOnceWith("/api/me/startup", expect.objectContaining({
    cache: "no-store", credentials: "omit", headers: { Authorization: "Bearer token" },
  }));
});

it.each([
  { consent: null }, { consent: { ...notice, accepted: "true" } },
  { consent: { ...notice, notice: [] } }, { children: null }, { children: [{}] }, { uid: "another-account" },
])("rejects malformed or cross-account bootstrap data: %j", async change => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({
    uid: "account", role: "caregiver", consent: notice, children: [], ...change,
  }) }));
  await expect(getCurrentAccount()).rejects.toMatchObject({ accessStatus: "unavailable" });
});

it("does not expose a late bootstrap response after account replacement", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => {
    auth.currentUser = { uid: "replacement" };
    return { uid: "account", role: "caregiver", consent: notice, children: [] };
  } }));
  await expect(getCurrentAccount()).rejects.toThrow("Account changed");
});
