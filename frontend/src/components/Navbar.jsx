export function Navbar({ isAuthenticated, onLogin, onSignup, onAccount }) {
  return (
    <header>
      <span>Parenting Voice Assistant</span>
      <nav aria-label="Account">
        {isAuthenticated ? (
          <button type="button" onClick={onAccount}>
            My Account
          </button>
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
