// this file calls our python backend endpoints using the logged-in user's firebase token.
// it is imported in pages/AccountPage.jsx to test and verify backend access.
import { auth } from "./firebase";

export async function getCurrentAccount() {
  // ask our python backend about the current user.
  const user = auth.currentUser;

  if (!user) {
    throw new Error("Log in first.");
  }

  // get firebase's proof of login without printing it or saving our own copy.
  const token = await user.getIdToken();

  // send the login token through vite to fastapi for checking.
  const response = await fetch("/api/me", {
    method: "GET",
    credentials: "omit",
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  // ignore the response if the user logged out or changed accounts while waiting.
  if (auth.currentUser !== user) {
    throw new Error("Account changed. Please try again.");
  }

  const body = await response.json();

  // check whether the server refused the request and report its message to the page.
  if (!response.ok) {
    throw new Error(body.detail || "Account check failed.");
  }

  return body;
}
