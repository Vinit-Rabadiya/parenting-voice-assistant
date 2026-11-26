import AdminFeedbackSummary from "../components/AdminFeedbackSummary";
import { lazy, Suspense, useRef, useState } from "react";
import "./AdminPage.css";

const AdminFeedbackImprovements = lazy(() => import("../components/AdminFeedbackImprovements"));

export default function AdminPage() {
  const caseEditor = useRef(null);
  const [investigationDisabled, setInvestigationDisabled] = useState(true);
  return <section className="admin-page" aria-labelledby="admin-title">
    <header className="admin-page-heading">
      <p className="admin-eyebrow">FEEDBACK AND IMPROVEMENTS</p>
      <h1 id="admin-title">Administrator dashboard</h1>
    </header>
    <AdminFeedbackSummary onInvestigate={category => caseEditor.current?.startInvestigation(category)}
      investigationDisabled={investigationDisabled} />
    <Suspense fallback={<p role="status">Loading improvement workspace...</p>}>
      <AdminFeedbackImprovements ref={caseEditor} onInvestigationDisabledChange={setInvestigationDisabled} />
    </Suspense>
  </section>;
}
