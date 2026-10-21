// calls services/api.js so app.jsx can share backend-verified access status across screens.
import { useCallback, useEffect, useState } from "react";
import { getCurrentAccount } from "../services/api";

// only show verified after the backend accepts the current email and mfa session.
export default function useAccountAccess(user) {
  const [result, setResult] = useState({ user: null, verified: false, error: "" });
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    if (!user) return;
    let active = true;
    let controller;
    let accessConfirmed = false;

    async function check() {
      controller?.abort();
      const request = new AbortController();
      controller = request;
      const timer = setTimeout(() => {
        request.abort();
        if (active && controller === request) {
          setResult({ user, attempt, verified: false, status: "unavailable", error: "Unable to connect. Please retry." });
        }
      }, 5000);
      try {
        await getCurrentAccount(request.signal);
        if (active && controller === request && !request.signal.aborted) {
          accessConfirmed = true;
          setResult({ user, attempt, verified: true, status: "verified", error: "" });
        }
      } catch (cause) {
        if (active && controller === request && !request.signal.aborted) {
          const status = cause.accessStatus === "verification_required" ? "verification_required" : "unavailable";
          setResult({
            user, attempt, verified: false, status,
            error: status === "verification_required" ? cause.message : "Unable to connect. Please retry.",
          });
        }
      } finally {
        clearTimeout(timer);
      }
    }

    void check();
    // Retry unfinished setup on focus, but reuse confirmed access in this session.
    const checkUnconfirmedAccess = () => { if (!accessConfirmed) void check(); };
    window.addEventListener("focus", checkUnconfirmedAccess);
    return () => {
      active = false;
      controller?.abort();
      window.removeEventListener("focus", checkUnconfirmedAccess);
    };
  }, [user, attempt]);

  if (!user) return { verified: false, checking: false, error: "" };
  if (result.user !== user || result.attempt !== attempt) return { verified: false, checking: true, status: "checking", error: "", retry };
  return { verified: result.verified, checking: false, status: result.status, error: result.error, retry };
}
