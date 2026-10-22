export default function ChatLoading() {
  return <div className="access-loading-screen chat-startup-loading" role="status" aria-label="Loading chat">
    <span className="access-spinner" aria-hidden="true" />
    <span className="visually-hidden">Loading chat…</span>
  </div>;
}
