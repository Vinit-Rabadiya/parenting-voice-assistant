// calls services/api.js so app.jsx can share backend-verified access status across screens.
import { useEffect, useState } from "react";
import { getCurrentAccount } from "../services/api";

// only show verified after the backend accepts the current email and mfa session.
export default function useAccountAccess(user) {
  const [result, setResult] = useState({ user: null, verified: false, error: "" });

  useEffect(() => {
    if (!user) return;
    let active = true;
    let controller;

    async function check() {
      controller?.abort();
      const request = new AbortController();
      controller = request;
      const timer = setTimeout(() => {
        request.abort();
        if (active && controller === request) {
          setResult({ user, verified: false, error: "Could not verify access right now. Return to this window to check again." });
        }
      }, 15000);
      try {
        await getCurrentAccount(request.signal);
        if (active && controller === request && !request.signal.aborted) {
          setResult({ user, verified: true, error: "" });
        }
      } catch (cause) {
        if (active && controller === request) {
          setResult({
            user, verified: false,
            error: request.signal.aborted
              ? "Could not verify access right now. Return to this window to check again."
              : cause.message || "Could not verify account access.",
          });
        }
      } finally {
        clearTimeout(timer);
      }
    }

    void check();
    // returning from email verification or account setup refreshes the badge.
    window.addEventListener("focus", check);
    return () => {
      active = false;
      controller?.abort();
      window.removeEventListener("focus", check);
    };
  }, [user]);

  if (!user) return { verified: false, checking: false, error: "" };
  if (result.user !== user) return { verified: false, checking: true, error: "" };
  return { verified: result.verified, checking: false, error: result.error };
}
