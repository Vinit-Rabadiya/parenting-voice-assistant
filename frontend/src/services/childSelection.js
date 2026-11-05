// Store only a profile ID; the authenticated profile list validates it on restore.
const key = (userId) => `selected-child:${userId}`;

export function publishChildProfiles(userId, children) {
  if (userId) window.dispatchEvent(new CustomEvent("child-profiles-updated", { detail: { userId, children } }));
}

export function readChildSelection(userId) {
  if (!userId) return null;
  try { return localStorage.getItem(key(userId)); }
  catch { return null; }
}

export function saveChildSelection(userId, childId) {
  if (!userId) return;
  try {
    if (childId) localStorage.setItem(key(userId), childId);
    else localStorage.removeItem(key(userId));
  } catch { /* Profile selection still works when browser storage is unavailable. */ }
}
