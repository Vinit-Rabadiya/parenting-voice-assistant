// Calls the Python backend endpoints using the signed-in user's Firebase token.
// the account-access hook uses this to verify the current session automatically.
import { auth } from "./firebase";

function accessError(message, status) {
  const error = new Error(message);
  error.accessStatus = status;
  return error;
}

export async function getCurrentAccount(signal) {
  // Request the current user's account details from the Python backend.
  const user = auth.currentUser;

  if (!user) {
    throw new Error("Log in first.");
  }

  // Obtain the Firebase authentication token without logging or persisting it.
  const token = await user.getIdToken();
  signal?.throwIfAborted();
  if (auth.currentUser !== user) throw accessError("Account changed. Please try again.", "unavailable");

  // send the login token through vite to fastapi for checking.
  let response;
  try {
    response = await fetch("/api/me", {
    method: "GET",
    signal,
    credentials: "omit",
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    });
  } catch (cause) {
    if (signal?.aborted) throw cause;
    throw new Error("Unable to connect. Please retry.", { cause });
  }

  // ignore the response if the user logged out or changed accounts while waiting.
  if (auth.currentUser !== user) {
    throw new Error("Account changed. Please try again.");
  }

  let body;
  try {
    body = await response.json();
  } catch (cause) {
    if (signal?.aborted) throw cause;
    throw new Error("Unable to check access. Please retry.", { cause });
  }
  signal?.throwIfAborted();
  if (auth.currentUser !== user) {
    throw new Error("Account changed. Please try again.");
  }

  // check whether the server refused the request and report its message to the page.
  if (!response.ok) {
    const verificationRequired = response.status === 401 || response.status === 403;
    throw accessError(verificationRequired && typeof body.detail === "string" ? body.detail
      : "Unable to connect. Please retry.", verificationRequired ? "verification_required" : "unavailable");
  }

  if (body?.uid !== user.uid) throw accessError("Unable to confirm account access. Please retry.", "unavailable");

  return body;
}
