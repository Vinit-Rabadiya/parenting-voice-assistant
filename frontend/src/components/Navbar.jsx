// receives account status and navigation callbacks from app.jsx to display the shared header.
import "./Navbar.css";

export function Navbar({ isAuthenticated, displayName, accountAccess, onLogin, onSignup, onAccount, onHome }) {
  return (
    <header className="site-navbar">
      <button type="button" className="site-brand" onClick={onHome}>Parenting Voice Assistant</button>
      <nav aria-label="Account">
        {isAuthenticated ? (
          <>
            <div className="navbar-identity">
              <span className="navbar-name">{displayName || "Your account"}</span>
              <span className={`navbar-verification${accountAccess?.verified ? " is-verified" : ""}`}>
                {accountAccess?.checking ? "Checking verification…" : accountAccess?.verified ? "Verified" : "Verification required"}
              </span>
            </div>
            <button type="button" onClick={onAccount}>My Account</button>
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
