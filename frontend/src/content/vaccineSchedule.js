import { sourceCheckIsCurrent } from "./vaccineLearning";

export const scheduleCheckedOn = "2026-11-07";
export const reportingYear = 2025;
export const scheduleSources = [
  {
    title: "WHO: Kenya vaccination schedule (country-reported data)",
    url: "https://immunizationdata.who.int/global/wiise-detail-page/vaccination-schedule-for-country_name?ISO_3_CODE=KEN",
  },
  {
    title: "Kenya Ministry of Health: Measles-rubella and typhoid vaccination",
    url: "https://www.health.go.ke/node/1955",
  },
];

const bcg = { entry: "bcg", name: "BCG" };
const opv = { entry: "polio", name: "Oral polio vaccine (OPV)" };
const ipv = { entry: "polio", name: "Inactivated polio vaccine (IPV)" };
const penta = { entry: "pentavalent", name: "Pentavalent" };
const pcv = { entry: "pcv", name: "Pneumococcal vaccine (PCV)" };
const rota = { entry: "rotavirus", name: "Rotavirus" };
const mr = { entry: "mr", name: "Measles-rubella (MR)" };
const tcv = { entry: "tcv", name: "Typhoid conjugate vaccine (TCV)" };
const malaria = { entry: "malaria", name: "Malaria vaccine",
  condition: "Only in eligible programme areas. The clinic confirms local eligibility and product." };
const yellowFever = { entry: "yellow-fever", name: "Yellow fever vaccine",
  condition: "Only in designated risk areas. The clinic confirms eligibility." };

// Programme visits, not due-dose calculations. Months remain calendar months.
export const visits = [
  { id: "birth", unit: "birth", age: 0, vaccines: [bcg, opv] },
  { id: "week-6", unit: "weeks", age: 6, vaccines: [opv, penta, pcv, rota] },
  { id: "week-10", unit: "weeks", age: 10, vaccines: [opv, penta, pcv, rota] },
  { id: "week-14", unit: "weeks", age: 14, vaccines: [opv, penta, pcv, rota, ipv] },
  { id: "month-6", unit: "months", age: 6, vaccines: [malaria] },
  { id: "month-7", unit: "months", age: 7, vaccines: [malaria] },
  { id: "month-9", unit: "months", age: 9, vaccines: [mr, ipv, tcv, malaria, yellowFever] },
  { id: "month-18", unit: "months", age: 18, vaccines: [mr] },
  { id: "month-24", unit: "months", age: 24, vaccines: [malaria] },
];

export const scheduleIsCurrent = (now = new Date()) => sourceCheckIsCurrent(scheduleCheckedOn, now);

export function visitLabel(visit, display = "all") {
  if (visit.unit === "birth") return "At birth (day 0)";
  if (visit.unit === "months") return `${visit.age} months`;
  return display === "days" ? `Day ${visit.age * 7} (${visit.age} weeks)`
    : `${visit.age} weeks (${visit.age * 7} days)`;
}

export function visitsForDisplay(display) {
  if (display === "days") return visits.filter(visit => visit.unit !== "months");
  if (display === "weeks" || display === "months") return visits.filter(visit => visit.unit === display);
  return visits;
}
