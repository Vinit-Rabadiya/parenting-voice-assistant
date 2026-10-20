// Calls the Python backend endpoints using the signed-in user's Firebase token.
// the account-access hook uses this to verify the current session automatically.
import { auth } from "./firebase";

export async function getCurrentAccount(signal) {
  // Request the current user's account details from the Python backend.
  const user = auth.currentUser;

  if (!user) {
    throw new Error("Log in first.");
  }

  // Obtain the Firebase authentication token without logging or persisting it.
  const token = await user.getIdToken();
  signal?.throwIfAborted();

  // send the login token through vite to fastapi for checking.
  const response = await fetch("/api/me", {
    method: "GET",
    signal,
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
  signal?.throwIfAborted();
  if (auth.currentUser !== user) {
    throw new Error("Account changed. Please try again.");
  }

  // check whether the server refused the request and report its message to the page.
  if (!response.ok) {
    throw new Error(body.detail || "Account check failed.");
  }

  return body;
}
