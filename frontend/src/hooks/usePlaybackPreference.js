import { useCallback, useSyncExternalStore } from "react";

const prefix = "guidance-autoplay:v1:";
const changed = "guidance-playback-preference-changed";
// Failed storage writes still apply in the current tab, separately per account.
const temporary = new Map();

function read(userId) {
  if (!userId) return true;
  const key = prefix + userId;
  if (temporary.has(key)) return temporary.get(key);
  try {
    const saved = window.localStorage.getItem(key);
    return saved === null || saved === "true";
  } catch {
    // Keep manual Listen available without starting unexpected audio.
    return false;
  }
}

export function clearPlaybackPreference(userId) {
  if (!userId) return;
  const key = prefix + userId;
  temporary.delete(key);
  try { window.localStorage.removeItem(key); }
  catch { temporary.set(key, false); }
  window.dispatchEvent(new CustomEvent(changed, { detail: key }));
}

export default function usePlaybackPreference(userId) {
  const subscribe = useCallback((notify) => {
    const key = prefix + userId;
    function update(event) {
      if (event.type === "storage") {
        if (event.key !== key && event.key !== null) return;
        temporary.delete(key);
      } else if (event.detail !== key) return;
      notify();
    }
    window.addEventListener(changed, update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener(changed, update);
      window.removeEventListener("storage", update);
    };
  }, [userId]);
  const snapshot = useCallback(() => read(userId), [userId]);
  const automatic = useSyncExternalStore(subscribe, snapshot, () => true);
  const setAutomatic = useCallback((enabled) => {
    if (!userId || typeof enabled !== "boolean") return false;
    const key = prefix + userId;
    let saved = true;
    try {
      window.localStorage.setItem(key, String(enabled));
      temporary.delete(key);
    } catch {
      temporary.set(key, enabled);
      saved = false;
    }
    window.dispatchEvent(new CustomEvent(changed, { detail: key }));
    return saved;
  }, [userId]);
  return { automatic, setAutomatic };
}
