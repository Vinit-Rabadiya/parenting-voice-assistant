import AdminFeedbackSummary from "../components/AdminFeedbackSummary";
import "./AdminPage.css";

export default function AdminPage() {
  return <section className="admin-page" aria-labelledby="admin-title">
    <header className="admin-page-heading">
      <p className="admin-eyebrow">FEEDBACK OVERVIEW</p>
      <h1 id="admin-title">Administrator dashboard</h1>
    </header>
    <AdminFeedbackSummary />
  </section>;
}
