import { auth } from "./firebase";

export async function getCurrentAccount() {
  const user = auth.currentUser;

  if (!user) {
    throw new Error("Log in first.");
  }

  const token = await user.getIdToken();

  const response = await fetch("/api/me", {
    method: "GET",
    credentials: "omit",
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (auth.currentUser !== user) {
    throw new Error("Account changed. Please try again.");
  }

  const body = await response.json();

  if (!response.ok) {
    throw new Error(body.detail || "Account check failed.");
  }

  return body;
}
