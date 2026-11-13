import AdminFeedbackSummary from "../components/AdminFeedbackSummary";
import { lazy, Suspense } from "react";
import "./AdminPage.css";

const AdminFeedbackImprovements = lazy(() => import("../components/AdminFeedbackImprovements"));

export default function AdminPage() {
  return <section className="admin-page" aria-labelledby="admin-title">
    <header className="admin-page-heading">
      <p className="admin-eyebrow">FEEDBACK AND IMPROVEMENTS</p>
      <h1 id="admin-title">Administrator dashboard</h1>
    </header>
    <AdminFeedbackSummary />
    <Suspense fallback={<p role="status">Loading improvement workspace...</p>}><AdminFeedbackImprovements /></Suspense>
  </section>;
}
