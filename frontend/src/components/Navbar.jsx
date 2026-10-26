// receives account status and navigation callbacks from app.jsx to display the shared header.
import "./Navbar.css";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { stopGuidanceAudio } from "../hooks/useGuidanceAudio";

export function Navbar({ isAuthenticated, displayName, accountAccess, onLogin, onSignup, onAccount, onHome }) {
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const menuRef = useRef(null);
  const triggerRef = useRef(null);
  useEffect(() => {
    if (!open) return;
    function outside(event) { if (!menuRef.current?.contains(event.target)) setOpen(false); }
    function escape(event) {
      if (event.key === "Escape") { setOpen(false); triggerRef.current?.focus(); }
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("focusin", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("focusin", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  async function signOut() {
    if (busy) return;
    setBusy(true); setError("");
    try { await logout(); stopGuidanceAudio(); setOpen(false); }
    catch { setError("Could not log out. Please try again."); }
    finally { setBusy(false); }
  }
  return (
    <header className={`site-navbar${accountAccess?.role === "administrator" ? " site-navbar--admin" : ""}`}>
      <button type="button" className="site-brand" onClick={onHome}>Parenting Voice Assistant</button>
      <nav aria-label="Account">
        {isAuthenticated ? (
          <>
            <div className="navbar-identity">
              <span className="navbar-name">{displayName || "Your account"}</span>
              <span className={`navbar-verification${accountAccess?.verified ? " is-verified" : ""}`}>
                {accountAccess?.checking ? "Loading…" : accountAccess?.verified ? "Verified"
                  : accountAccess?.status === "unavailable" ? "Service unavailable" : "Verification required"}
              </span>
            </div>
            {accountAccess?.role === "administrator" && <button type="button" onClick={onHome}>Dashboard</button>}
            <div className="navbar-account-menu" ref={menuRef}>
              <button type="button" ref={triggerRef} aria-expanded={open} aria-controls="navbar-account-options"
                onClick={() => setOpen((value) => !value)}>My Account</button>
              {open && <div id="navbar-account-options" className="navbar-account-options">
                <button type="button" disabled={busy} onClick={() => { setOpen(false); onAccount(); }}>Settings</button>
                <button type="button" className="navbar-logout" disabled={busy} onClick={signOut}>{busy ? "Logging out…" : "Log Out"}</button>
                {error && <p role="alert">{error}</p>}
              </div>}
            </div>
          </>
        ) : (
          <>
            <button type="button" onClick={onLogin}>
              Log in
            </button>
            <button type="button" onClick={onSignup}>
              Sign up
            </button>
          </>
        )}
      </nav>
    </header>
  );
}
