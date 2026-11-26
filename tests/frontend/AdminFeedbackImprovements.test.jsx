import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AdminFeedbackImprovements from "../../frontend/src/components/AdminFeedbackImprovements";
import AdminPage from "../../frontend/src/pages/AdminPage";
import { createFeedbackImprovement, deleteFeedbackImprovement, getFeedbackSummary, listFeedbackImprovements, updateFeedbackImprovement } from "../../frontend/src/services/caregiving";

vi.mock("../../frontend/src/services/caregiving", () => ({ createFeedbackImprovement: vi.fn(), deleteFeedbackImprovement: vi.fn(),
  getFeedbackSummary: vi.fn(), listFeedbackImprovements: vi.fn(), updateFeedbackImprovement: vi.fn() }));

const id = "a".repeat(32);
const scores = { faithfulness: 4, helpfulness: 3, age_fit: 4, clarity: 4, safety: 4 };
const review = { answer: "Fictional example answer", model: "test-model", prompt_revision: "prompt-v1",
  corpus_revision: "corpus-v1", report_reference: "synthetic-run.json", scores,
  faithfulness_not_applicable: false, faithfulness_note: "" };
const draft = { title: "Repeated play advice", category: "repeated_advice", scenario: "A fictional caregiver asks for another play idea.",
  expected_behavior: "Offer a distinct reviewed idea.", fictional_date_of_birth: "2026-05-10", evaluation_date: "2026-11-10",
  fictional_confirmed: true, status: "investigating", change_area: "prompt", change_summary: "Clarify distinct alternatives.",
  change_reference: "synthetic-change", baseline: review, candidate: { ...review, answer: "A different fictional answer", prompt_revision: "prompt-v2" },
  checks: { issue_resolved: true, sources_checked: true, age_checked: true, safety_checked: true, regressions_passed: true },
  evaluation_notes: "Source and regression evidence reviewed for this fictional example.", release_revision: "", deployment_checked: false, release_notes: "" };
const record = (content = draft, version = 1) => ({ id, version, content, created_at: "2026-11-11T08:00:00Z", updated_at: "2026-11-11T08:00:00Z", released_at: null });

beforeEach(() => {
  vi.resetAllMocks();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  listFeedbackImprovements.mockResolvedValue({ items: [], next_cursor: null });
  deleteFeedbackImprovement.mockResolvedValue({});
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function openCase(content = draft) {
  listFeedbackImprovements.mockResolvedValue({ items: [record(content)], next_cursor: null });
  render(<AdminFeedbackImprovements />);
  fireEvent.click(await screen.findByRole("button", { name: /Repeated play advice/ }));
}

function openEvaluation() {
  fireEvent.click(screen.getByRole("button", { name: "Test a fix" }));
}

it("explains how feedback leads to reviewed changes without claiming automatic training", async () => {
  render(<AdminFeedbackImprovements />);
  await screen.findByText("No improvement cases on this page.");
  expect(screen.getByText(/does not train or deploy a model/)).toBeTruthy();
  expect(listFeedbackImprovements).toHaveBeenCalledTimes(1);
  expect(createFeedbackImprovement).not.toHaveBeenCalled();
});

it("creates an administrator-authored scenario without asking for dates", async () => {
  createFeedbackImprovement.mockImplementation(async content => record({
    ...content, fictional_date_of_birth: null, evaluation_date: null,
  }));
  render(<AdminFeedbackImprovements />);
  await screen.findByText("No improvement cases on this page.");
  fireEvent.click(screen.getByRole("button", { name: "New improvement case" }));
  expect(screen.queryByLabelText("Date of birth")).toBeNull();
  expect(screen.queryByLabelText("Evaluation date")).toBeNull();
  expect(screen.queryByRole("button", { name: "Test a fix" })).toBeNull();
  expect(screen.queryByLabelText("Baseline answer text")).toBeNull();
  for (const [label, value] of [["Case title", "Play advice concern"], ["Scenario", "A caregiver asks for a new play idea"],
    ["Expected answer behavior", "Offer different age-appropriate guidance"]]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
  fireEvent.click(screen.getByLabelText(/I wrote this case without caregiver identifiers/));
  fireEvent.click(screen.getByRole("button", { name: "Save investigation" }));
  await screen.findByText("Improvement case saved.");
  expect(createFeedbackImprovement.mock.calls[0][0]).toMatchObject({ title: "Play advice concern", fictional_confirmed: true, status: "investigating" });
  expect(createFeedbackImprovement.mock.calls[0][0]).not.toHaveProperty("fictional_date_of_birth");
  expect(createFeedbackImprovement.mock.calls[0][0]).not.toHaveProperty("evaluation_date");
  expect(createFeedbackImprovement.mock.calls[0][0].caregiver_uid).toBeUndefined();
  openEvaluation();
  expect(screen.getByLabelText("Baseline answer text")).toBeTruthy();
  expect(screen.queryByLabelText("Case title")).toBeNull();
  expect(screen.queryByLabelText("Deployed commit")).toBeNull();
  fireEvent.change(screen.getByLabelText("Baseline answer text"), { target: { value: "Unsaved test answer" } });
  fireEvent.click(screen.getByRole("button", { name: "Concern" }));
  openEvaluation();
  expect(screen.getByLabelText("Baseline answer text").value).toBe("Unsaved test answer");
});

it("starts and saves a case from a reported reason in the dashboard", async () => {
  const comment = "My child has a private name.";
  getFeedbackSummary.mockResolvedValue({ unit: "Saved feedback per answer", ratings: [], legacy_helpfulness: [],
    reasons: [{ label: "Did not answer the message", count: 1 }, { label: "Unclear", count: 0 }],
    comments: [{ comment, rating: 2, helpful: null, reasons: ["Did not answer the message"] }], comment_count: 1 });
  createFeedbackImprovement.mockImplementation(async content => record(content));
  render(<AdminPage />);
  const investigateButton = await screen.findByRole("button", { name: "Investigate: Did not answer the message" });
  expect(screen.queryByRole("button", { name: "Investigate: Unclear" })).toBeNull();
  await waitFor(() => expect(investigateButton.disabled).toBe(false));
  fireEvent.click(investigateButton);
  expect(screen.getByLabelText("Feedback category").value).toBe("did_not_answer");
  expect(screen.getByLabelText("Scenario").value).toBe("");
  expect(createFeedbackImprovement).not.toHaveBeenCalled();

  for (const [label, value] of [["Case title", "Answer missed the concern"], ["Scenario", "The caregiver asks for an alternative"],
    ["Expected answer behavior", "Answer the follow-up with a distinct option"]]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
  fireEvent.click(screen.getByLabelText(/I wrote this case without caregiver identifiers/));
  fireEvent.click(screen.getByRole("button", { name: "Save investigation" }));
  await screen.findByText("Improvement case saved.");
  const submitted = createFeedbackImprovement.mock.calls[0][0];
  expect(submitted).toMatchObject({ category: "did_not_answer", status: "investigating" });
  expect(JSON.stringify(submitted)).not.toContain(comment);
  openEvaluation();
  expect(screen.getByLabelText("Baseline answer text")).toBeTruthy();
});

it("does not advance an incomplete evaluation", async () => {
  await openCase({ ...draft, baseline: { ...review, answer: "" } });
  openEvaluation();
  fireEvent.click(screen.getByRole("button", { name: "Record successful evaluation" }));
  await screen.findByRole("alert");
  expect(screen.getByText(/Complete both answers/)).toBeTruthy();
  expect(updateFeedbackImprovement).not.toHaveBeenCalled();
});

it("records evaluation, release and reopening with the latest saved revision", async () => {
  await openCase();
  openEvaluation();
  updateFeedbackImprovement.mockImplementation(async (_, content, version) => record(content, version + 1));
  fireEvent.click(screen.getByRole("button", { name: "Record successful evaluation" }));
  await screen.findByRole("button", { name: "Record release" });
  expect(updateFeedbackImprovement.mock.calls[0][2]).toBe(1);
  expect(updateFeedbackImprovement.mock.calls[0][1]).toMatchObject({
    fictional_date_of_birth: draft.fictional_date_of_birth, evaluation_date: draft.evaluation_date,
  });
  expect(screen.queryByLabelText("Case title")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Concern" }));
  expect(screen.getByLabelText("Case title").closest("fieldset").disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Release record" }));
  fireEvent.change(screen.getByLabelText("Deployed commit"), { target: { value: "b".repeat(40) } });
  fireEvent.change(screen.getByLabelText("Release notes"), { target: { value: "Checked the applied correction." } });
  fireEvent.click(screen.getByLabelText("I checked that this correction is deployed."));
  fireEvent.click(screen.getByRole("button", { name: "Record release" }));
  await screen.findByText("Release recorded. This does not deploy or retrain a model.");
  expect(updateFeedbackImprovement.mock.calls[1][2]).toBe(2);
  expect(updateFeedbackImprovement.mock.calls[1][1].status).toBe("released");
  updateFeedbackImprovement.mockImplementation(async (_, content, version) => record({ ...content,
    checks: Object.fromEntries(Object.keys(content.checks).map(key => [key, false])), release_revision: "", deployment_checked: false, release_notes: "" }, version + 1));
  fireEvent.click(screen.getByText("Case actions"));
  fireEvent.click(screen.getByRole("button", { name: "Reopen investigation" }));
  await screen.findByRole("button", { name: "Save investigation" });
  expect(updateFeedbackImprovement.mock.calls[2][2]).toBe(3);
  expect(screen.getByLabelText("Case title").closest("fieldset").disabled).toBe(false);
});

it("keeps a stale-write conflict visible instead of replacing another review", async () => {
  await openCase();
  updateFeedbackImprovement.mockRejectedValue(Object.assign(new Error("This case changed. Refresh before saving again."), { status: 409 }));
  fireEvent.click(screen.getByRole("button", { name: "Save investigation" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "This case changed. Refresh before saving again.");
  expect(screen.getByLabelText("Case title").value).toBe(draft.title);
});

it("keeps edited review content when discarding changes is cancelled", async () => {
  await openCase();
  fireEvent.change(screen.getByLabelText("Case title"), { target: { value: "Unsaved correction" } });
  window.confirm.mockReturnValue(false);
  fireEvent.click(screen.getByRole("button", { name: "Close editor" }));
  expect(screen.getByLabelText("Case title").value).toBe("Unsaved correction");
  fireEvent.click(screen.getByRole("button", { name: "New improvement case" }));
  expect(screen.getByLabelText("Case title").value).toBe("Unsaved correction");
  window.confirm.mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "Close editor" }));
  expect(screen.queryByLabelText("Case title")).toBeNull();
});

it("requires a reason for source support being inapplicable and sends no invented score", async () => {
  await openCase();
  openEvaluation();
  fireEvent.click(screen.getByText("Candidate evidence and scores"));
  fireEvent.click(screen.getByLabelText("Candidate source support is not applicable (no supplied references)."));
  expect(screen.getByLabelText("Candidate source support score").disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Record successful evaluation" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Complete both answers"));
  expect(updateFeedbackImprovement).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Candidate source-support applicability note"), { target: { value: "Fixed boundary response without reference passages." } });
  updateFeedbackImprovement.mockImplementation(async (_, content, version) => record(content, version + 1));
  fireEvent.click(screen.getByRole("button", { name: "Record successful evaluation" }));
  await screen.findByRole("button", { name: "Record release" });
  expect(updateFeedbackImprovement.mock.calls[0][1].candidate.scores.faithfulness).toBeNull();
});

it("ignores a timed-out save when its result arrives after a newer case is opened", async () => {
  await openCase();
  vi.useFakeTimers(); let complete;
  updateFeedbackImprovement.mockReturnValue(new Promise(resolve => { complete = resolve; }));
  fireEvent.click(screen.getByRole("button", { name: "Save investigation" }));
  const signal = updateFeedbackImprovement.mock.calls[0][3];
  await act(async () => vi.advanceTimersByTimeAsync(20000));
  expect(screen.getByRole("alert").textContent).toContain("Saving timed out");
  expect(signal.aborted).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "New improvement case" }));
  await act(async () => complete(record({ ...draft, title: "Late saved result" }, 2)));
  expect(screen.getByLabelText("Case title").value).toBe("");
  expect(screen.queryByText("Improvement case saved.")).toBeNull();
});

it("removes own review content when access is refused on refresh", async () => {
  await openCase();
  listFeedbackImprovements.mockRejectedValue(Object.assign(new Error("denied"), { status: 403 }));
  fireEvent.click(screen.getByRole("button", { name: "Refresh cases" }));
  await screen.findByText(/Administrator access is unavailable/);
  expect(screen.queryByLabelText("Case title")).toBeNull();
  expect(screen.queryByText(draft.title)).toBeNull();
  expect(screen.getByRole("button", { name: "New improvement case" }).disabled).toBe(true);
});

it("deletes only the selected saved version and refreshes the list", async () => {
  await openCase();
  listFeedbackImprovements.mockResolvedValue({ items: [], next_cursor: null });
  fireEvent.click(screen.getByText("Case actions"));
  fireEvent.click(screen.getByRole("button", { name: "Delete case" }));
  await screen.findByText("Improvement case deleted.");
  expect(deleteFeedbackImprovement.mock.calls[0].slice(0, 2)).toEqual([id, 1]);
  expect(screen.queryByLabelText("Case title")).toBeNull();
});

it("times out list loading and ignores a late result", async () => {
  vi.useFakeTimers(); let complete;
  listFeedbackImprovements.mockReturnValue(new Promise(resolve => { complete = resolve; }));
  render(<AdminFeedbackImprovements />);
  const signal = listFeedbackImprovements.mock.calls[0][0];
  await act(async () => vi.advanceTimersByTimeAsync(20000));
  expect(screen.getByText(/took too long/)).toBeTruthy(); expect(signal.aborted).toBe(true);
  await act(async () => complete({ items: [record()], next_cursor: null }));
  expect(screen.queryByText(draft.title)).toBeNull();
});

it("loads older cases using the server cursor", async () => {
  listFeedbackImprovements.mockResolvedValueOnce({ items: [record()], next_cursor: id }).mockResolvedValue({ items: [], next_cursor: null });
  render(<AdminFeedbackImprovements />);
  fireEvent.click(await screen.findByRole("button", { name: "Older cases" }));
  await waitFor(() => expect(listFeedbackImprovements).toHaveBeenCalledTimes(2));
  expect(listFeedbackImprovements.mock.calls[1][1]).toBe(id);
});
