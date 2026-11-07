import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import VaccineSchedule, { VaccineTiming } from "../../frontend/src/components/VaccineSchedule";
import { reportingYear, scheduleCheckedOn, scheduleIsCurrent, visits, visitsForDisplay } from "../../frontend/src/content/vaccineSchedule";
import sourceReview from "../../data/evaluation/vaccine-schedule-learning-source-review.json";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-07T12:00:00Z"));
  vi.stubGlobal("fetch", vi.fn(() => { throw new Error("Schedule must not fetch"); }));
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

it("matches every displayed programme age to the independently captured WHO records", () => {
  const codes = { bcg: "BCG", pentavalent: "DTWPHIBHEPB", pcv: "PCV10", rotavirus: "ROTAVIRUS_1",
    mr: "MR", tcv: "TYPHOID_CONJ", malaria: "MALARIA", "yellow-fever": "YF" };
  const actual = {};
  for (const visit of visits) {
    const age = visit.unit === "birth" ? "B" : `${visit.unit === "weeks" ? "W" : "M"}${visit.age}`;
    for (const vaccine of visit.vaccines) {
      const code = vaccine.entry === "polio" ? (vaccine.name.includes("(OPV)") ? "OPV" : "IPV") : codes[vaccine.entry];
      expect(code).toBeTruthy();
      (actual[code] ||= []).push(age);
    }
  }
  expect(actual).toEqual(sourceReview.selected_age_codes);
  expect(scheduleCheckedOn).toBe(sourceReview.checked_on);
  expect(reportingYear).toBe(sourceReview.latest_reporting_year_returned);
});

it("shows sourced birth, week and calendar-month visits through the second birthday", () => {
  render(<VaccineSchedule onAsk={vi.fn()} onExplain={vi.fn()} />);
  expect(screen.getByRole("heading", { name: "At birth (day 0)" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "6 weeks (42 days)" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "24 months" })).toBeTruthy();
  expect(screen.getByText("7 November 2026").dateTime).toBe("2026-11-07");
  expect(screen.getByRole("link", { name: /WHO: Kenya vaccination schedule/ }).href).toContain("ISO_3_CODE=KEN");
  expect(fetch).not.toHaveBeenCalled();
  expect(visits).toHaveLength(9);
});

it("converts weeks to days exactly without inventing fixed-day equivalents for calendar months", () => {
  render(<VaccineSchedule onAsk={vi.fn()} onExplain={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Days", exact: true }));
  for (const label of ["At birth (day 0)", "Day 42 (6 weeks)", "Day 70 (10 weeks)", "Day 98 (14 weeks)"]) {
    expect(screen.getByRole("heading", { name: label })).toBeTruthy();
  }
  expect(screen.queryByRole("heading", { name: "9 months" })).toBeNull();
  expect(screen.getByText(/months are not fixed numbers of days/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Months", exact: true }));
  expect(screen.getByRole("heading", { name: "9 months" })).toBeTruthy();
  expect(screen.queryByText(/Day 270|Day 720/)).toBeNull();
  expect(visitsForDisplay("months").map(visit => visit.age)).toEqual([6, 7, 9, 18, 24]);
  fireEvent.click(screen.getByRole("button", { name: "Weeks", exact: true }));
  expect(visitsForDisplay("weeks").map(visit => visit.age)).toEqual([6, 10, 14]);
  expect(screen.queryByRole("heading", { name: "At birth (day 0)" })).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
});

it("keeps later IPV, rotavirus, TCV and regional vaccines at their reported programme ages", () => {
  render(<VaccineSchedule onAsk={vi.fn()} onExplain={vi.fn()} />);
  const week6 = screen.getByRole("heading", { name: "6 weeks (42 days)" }).closest(".vaccine-visit");
  expect(within(week6).queryByRole("button", { name: "Inactivated polio vaccine (IPV)" })).toBeNull();
  const week14 = screen.getByRole("heading", { name: "14 weeks (98 days)" }).closest(".vaccine-visit");
  expect(within(week14).getByRole("button", { name: "Rotavirus", exact: true })).toBeTruthy();
  expect(within(week14).getByRole("button", { name: "Inactivated polio vaccine (IPV)" })).toBeTruthy();
  const month9 = screen.getByRole("heading", { name: "9 months" }).closest(".vaccine-visit");
  expect(within(month9).getByRole("button", { name: "Typhoid conjugate vaccine (TCV)" })).toBeTruthy();
  expect(within(month9).getByRole("button", { name: "Inactivated polio vaccine (IPV)" })).toBeTruthy();
  expect(within(month9).getByText(/Only in eligible programme areas/)).toBeTruthy();
  expect(within(month9).getByText(/Only in designated risk areas/)).toBeTruthy();
});

it("opens the selected explanation and prepares age questions only on request", () => {
  const onAsk = vi.fn(), onExplain = vi.fn();
  const view = render(<VaccineSchedule onAsk={onAsk} onExplain={onExplain} />);
  fireEvent.click(screen.getAllByRole("button", { name: "Pneumococcal vaccine (PCV)" })[0]);
  expect(onExplain).toHaveBeenCalledExactlyOnceWith("pcv");
  expect(onAsk).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Open 6-week visit in new chat" }));
  expect(onAsk).toHaveBeenCalledExactlyOnceWith("Explain Kenya's routine vaccination visit at 6 weeks. What is each vaccine for?");
  view.rerender(<VaccineSchedule onAsk={onAsk} onExplain={onExplain} hasDraft />);
  expect(screen.getByRole("button", { name: "Open birth visit in new chat" }).disabled).toBe(true);
  view.rerender(<VaccineSchedule onAsk={onAsk} onExplain={onExplain} askDisabled />);
  expect(screen.getByRole("button", { name: "Open birth visit in new chat" }).disabled).toBe(true);
});

it("shows OPV and IPV separately within the combined polio explanation's timing", () => {
  render(<VaccineTiming entryId="polio" />);
  expect(screen.getByText("At birth (day 0)")).toBeTruthy();
  expect(screen.getByText("14 weeks (98 days)").parentElement.textContent).toContain("OPV) and Inactivated polio vaccine (IPV)");
  const month9 = screen.getByText("9 months").parentElement;
  expect(month9.textContent).toContain("IPV");
  expect(month9.textContent).not.toContain("OPV");
  expect(screen.getByText(/do not establish which doses/)).toBeTruthy();
});

it.each(["2026-11-06T12:00:00Z", "2027-02-06T12:00:00Z"])("withholds unchecked or expired schedule ages at %s", now => {
  vi.setSystemTime(new Date(now));
  expect(scheduleIsCurrent()).toBe(false);
  render(<VaccineSchedule onAsk={vi.fn()} onExplain={vi.fn()} />);
  expect(screen.getByRole("status").textContent).toContain("waiting for a source review");
  expect(screen.queryByRole("heading", { name: "9 months" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Open birth visit in new chat" })).toBeNull();
  expect(screen.getByRole("link", { name: /WHO: Kenya vaccination schedule/ })).toBeTruthy();
});
