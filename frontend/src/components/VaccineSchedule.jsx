import { useId, useState } from "react";
import { reportingYear, scheduleCheckedOn, scheduleIsCurrent, scheduleSources, visitLabel, visits, visitsForDisplay } from "../content/vaccineSchedule";

function ScheduleSources() {
  return <div className="vaccine-schedule-sources">
    <p className="vaccine-reviewed">Country-reported schedule: {reportingYear}. Timing sources checked: <time dateTime={scheduleCheckedOn}>
      {new Date(`${scheduleCheckedOn}T00:00:00Z`).toLocaleDateString("en-GB", {
        day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
      })}</time>.</p>
    <ul>{scheduleSources.map(source => <li key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a></li>)}</ul>
  </div>;
}

export function VaccineTiming({ entryId }) {
  const matching = visits.filter(visit => visit.vaccines.some(vaccine => vaccine.entry === entryId));
  if (!matching.length) return null;
  return <div className="vaccine-timing">
    <h4>Routine timing in Kenya</h4>
    {scheduleIsCurrent() ? <>
      <ul>{matching.map(visit => <li key={visit.id}><strong>{visitLabel(visit)}</strong>: {visit.vaccines
        .filter(vaccine => vaccine.entry === entryId).map(vaccine => vaccine.name).join(" and ")}</li>)}</ul>
      {matching[0].vaccines.filter(vaccine => vaccine.entry === entryId && vaccine.condition)
        .map(vaccine => <p key={vaccine.name} className="vaccine-note">{vaccine.condition}</p>)}
      <p>Programme ages do not establish which doses your baby has received or needs next. Your clinic checks the booklet.</p>
    </> : <p>Timing details are waiting for a source review. Ask your clinic to confirm appointments.</p>}
    <ScheduleSources />
  </div>;
}

export default function VaccineSchedule({ onExplain, onAsk, askDisabled, hasDraft }) {
  const [display, setDisplay] = useState("all");
  const titleId = useId();
  const current = scheduleIsCurrent();
  return <section className="vaccine-schedule" aria-labelledby={titleId}>
    <h3 id={titleId}>Kenya routine visits: birth to 24 months</h3>
    <p>Explore the programme ages below. This is not a list of vaccines due for your baby or a catch-up plan. The clinic confirms appointments, products and recorded doses.</p>
    <ScheduleSources />
    {current ? <>
      <div className="vaccine-view-switch" role="group" aria-label="Age units">
        {[["all", "All ages"], ["days", "Days"], ["weeks", "Weeks"], ["months", "Months"]].map(([value, label]) =>
          <button type="button" key={value} aria-pressed={display === value} onClick={() => setDisplay(value)}>{label}</button>)}
      </div>
      <p className="vaccine-note">{display === "days"
        ? "This view shows birth and exact day equivalents of week-based visits. Calendar-month visits are in Months; months are not fixed numbers of days."
        : display === "weeks" ? "Week-based visits are shown with exact day equivalents: 1 week = 7 days. Use Months for later calendar-month visits."
          : display === "months" ? "This view shows calendar-month visits. Birth and early week-based visits are in All ages or Days/Weeks. A calendar month is not a fixed number of weeks or days."
          : "Week-based visits retain their official week labels. Month-based visits stay in calendar months; they are not converted to approximate weeks or days."}</p>
      <ol className="vaccine-visits">{visitsForDisplay(display).map(visit => <li className="vaccine-visit" key={visit.id}>
        <h4>{visitLabel(visit, display)}</h4>
        <ul>{visit.vaccines.map(vaccine => <li key={vaccine.name}>
          <button type="button" className="vaccine-explain-link" onClick={() => onExplain(vaccine.entry)}>{vaccine.name}</button>
          {vaccine.condition && <p className="vaccine-note">{vaccine.condition}</p>}
        </li>)}</ul>
        <button type="button" disabled={askDisabled || hasDraft}
          onClick={() => onAsk(`Explain Kenya's routine vaccination visit at ${visit.unit === "birth" ? "birth" : `${visit.age} ${visit.unit}`}. What is each vaccine for?`)}>Open {visit.unit === "birth" ? "birth" : `${visit.age}-${visit.unit === "weeks" ? "week" : "month"}`} visit in new chat</button>
      </li>)}</ol>
      {hasDraft && <p>You have an unsent message. Send or clear it before opening a new vaccine chat.</p>}
      {askDisabled && <p>Read here, or return to chat when coaching is available to ask a question.</p>}
      <p>If a booklet or appointment differs from this overview, ask the clinic to reconcile it. Regional availability and vaccine products can differ.</p>
    </> : <p role="status">The age-based schedule is waiting for a source review. Please check the linked sources and confirm with your clinic.</p>}
  </section>;
}
