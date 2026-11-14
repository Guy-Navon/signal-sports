/** @typedef {"light" | "soft" | "dark"} Ground */
export const DEFAULT_GROUND = "light";
export const GROUND_STORAGE_KEY = "signal.ground";
/** @type {{ id: Ground, label: string }[]} */
export const GROUNDS = [
  { id: "light", label: "לבן" },
  { id: "soft", label: "רך" },
  { id: "dark", label: "כהה" },
];

/** @param {unknown} value @returns {Ground} */
export function normalizeGround(value) {
  return value === "soft" || value === "dark" ? value : DEFAULT_GROUND;
}

// Inject a getter so even accessing window.localStorage (SecurityError in some
// private/blocked contexts) is inside the catch. No storage access at import.
export function readGround(getStorage) {
  try {
    return normalizeGround(getStorage().getItem(GROUND_STORAGE_KEY));
  } catch {
    return DEFAULT_GROUND;
  }
}

export function saveGround(value, getStorage) {
  try {
    const ground = normalizeGround(value);
    getStorage().setItem(GROUND_STORAGE_KEY, ground);
    return ground;
  } catch {
    return DEFAULT_GROUND;
  }
}
