import { useEffect, useId, useRef, useState } from "react";
import { checkedOn, educationIsCurrent, entries } from "../content/vaccineLearning";
import useGuidanceAudio from "../hooks/useGuidanceAudio";
import VaccineSchedule, { VaccineTiming } from "./VaccineSchedule";
import "./VaccineLearning.css";

function Explanation({ entry, onAsk, askDisabled, hasDraft }) {
  const titleId = useId();
  const text = `${entry.title}. ${entry.text} ${entry.note || ""} Your clinic confirms which vaccines your baby needs using their vaccination record.`;
  const audio = useGuidanceAudio(text);
  const speaking = ["preparing", "playing"].includes(audio.state);
  return <section className="vaccine-explanation" aria-labelledby={titleId}>
    <p className="vaccine-category">{entry.category}</p>
    <h3 id={titleId}>{entry.title}</h3>
    <p>{entry.text}</p>
    {entry.note && <p className="vaccine-note">{entry.note}</p>}
    <button type="button" onClick={() => { if (speaking) audio.stop(); else audio.play(); }}>
      {speaking ? "Stop explanation audio" : "Listen to explanation"}
    </button>
    {audio.message && <p role="status">{audio.message}</p>}
    <VaccineTiming entryId={entry.id} />
    <h4>Check the evidence</h4>
    <ul>{entry.sources.map(source => <li key={source.url}>
      <a href={source.url} target="_blank" rel="noreferrer">{source.title}</a>
    </li>)}</ul>
    <div className="vaccine-follow-up">
      <h4>Still have a question?</h4>
      <p>{hasDraft ? "You have an unsent message. Send or clear it before adding a vaccine question."
        : askDisabled ? "You can read here. Return to chat when coaching is available to ask a follow-up."
          : "Start a new conversation with this question, then review and send it yourself."}</p>
      <button type="button" disabled={askDisabled || hasDraft} onClick={() => onAsk(entry.question)}>Open in new chat</button>
    </div>
  </section>;
}

export default function VaccineLearning({ onClose, onAsk, askDisabled = false, hasDraft = false }) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("how");
  const [view, setView] = useState("learn");
  const dialogRef = useRef(null);
  const closeRef = useRef(null);
  const titleId = useId();
  const descriptionId = useId();
  const searchId = useId();
  const current = educationIsCurrent();
  const checkedLabel = new Date(`${checkedOn}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
  });
  const query = search.trim().toLowerCase();
  const matches = entries.filter(entry => `${entry.title} ${entry.keywords}`.toLowerCase().includes(query));
  const entry = matches.find(item => item.id === selected) || matches[0];

  useEffect(() => {
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    closeRef.current?.focus();
    return () => {
      if (dialog.open) dialog.close();
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  return <dialog ref={dialogRef} className="vaccine-dialog" aria-labelledby={titleId} aria-describedby={descriptionId}
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClose={() => { if (!dialogRef.current?.open) onClose(); }}>
    <header className="vaccine-heading">
      <div><p className="vaccine-category">BABIES AGED 0–24 MONTHS · KENYA</p>
        <h2 id={titleId}>Understand my baby's vaccines</h2></div>
      <button type="button" ref={closeRef} onClick={onClose}>Close vaccine explanations</button>
    </header>
    <p id={descriptionId}>Understand names in the booklet and common vaccine questions. Your clinic confirms doses, eligibility and appointments using your baby's record.</p>
    <p className="vaccine-note">General education, not an assessment of symptoms. If your baby is unwell or you are worried, contact a health professional. For an emergency, seek immediate medical care.</p>
    <p className="vaccine-reviewed">Explanation sources checked: <time dateTime={checkedOn}>{checkedLabel}</time>. These explanations are not a personal vaccination schedule.</p>
    <div className="vaccine-view-switch" role="group" aria-label="Vaccine learning views">
      <button type="button" aria-pressed={view === "learn"} onClick={() => setView("learn")}>Vaccine explanations</button>
      <button type="button" aria-pressed={view === "age"} onClick={() => setView("age")}>By age: days, weeks and months</button>
    </div>
    {view === "age" ? <VaccineSchedule onAsk={onAsk} askDisabled={askDisabled} hasDraft={hasDraft}
      onExplain={id => { setSelected(id); setSearch(""); setView("learn"); }} /> : current ? <>
      <label className="vaccine-search" htmlFor={searchId}>Find a vaccine name or question
        <input id={searchId} type="search" maxLength={120} value={search} placeholder="Try PCV, polio or autism"
          onChange={event => setSearch(event.target.value)} />
      </label>
      <div className="vaccine-layout">
        <nav className="vaccine-topics" aria-label="Vaccine explanations">
          {["Vaccine names", "Common questions"].map(category => {
            const items = matches.filter(item => item.category === category);
            return items.length > 0 && <div key={category}><h3>{category}</h3>
              {items.map(item => <button type="button" key={item.id} aria-pressed={entry?.id === item.id}
                onClick={() => setSelected(item.id)}>{item.title}</button>)}
            </div>;
          })}
        </nav>
        {entry ? <Explanation key={entry.id} entry={entry} onAsk={onAsk} askDisabled={askDisabled} hasDraft={hasDraft} />
          : <p role="status">No matching explanation. Try a vaccine abbreviation from your booklet, or ask your clinic to clarify the entry.</p>}
      </div>
    </> : <section className="vaccine-review-needed" aria-label="Source review needed">
      <h3>These explanations are waiting for a source review</h3>
      <p>Please use the original sources below or ask your clinic. LittleCare is temporarily withholding the explanation cards.</p>
      <ul>{entries[0].sources.map(source => <li key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a></li>)}</ul>
    </section>}
  </dialog>;
}
