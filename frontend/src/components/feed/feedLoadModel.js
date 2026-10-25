// What the feed body and the connection strip say when loading fails (journey
// audit D5). A failed feed request used to render the normal empty state
// ("nothing new, the system is scanning") under a red strip carrying the raw
// English server error: the reader was told "error" and "nothing new" at once.
// Pure and node-tested; Feed.jsx and AppShell.jsx render it.

/**
 * @param {{ isBackendMode: boolean, isLoading: boolean, loadFailed: boolean, itemCount: number }} s
 * @returns {"loading" | "error" | "empty" | "items"}
 */
export function feedBodyState({ isBackendMode, isLoading, loadFailed, itemCount }) {
  if (itemCount > 0) return "items"; // keep what the reader already sees
  if (!isBackendMode) return "empty";
  if (isLoading) return "loading";
  return loadFailed ? "error" : "empty";
}

export const FEED_LOAD_ERROR = {
  title: "לא הצלחנו לטעון את הפיד",
  message: "יש בעיה בחיבור לשרת. נסו שוב בעוד רגע.",
  retryLabel: "נסו שוב",
};

/**
 * The strip under the masthead. Readers get plain Hebrew; the ops console keeps
 * the raw detail and the developer hint, which help there.
 * @param {{ area: string, message: string }} p  area: "product" or "ops"
 */
export function connectionErrorStrip({ area, message }) {
  if (area === "ops") {
    return { title: "שגיאה בחיבור לשרת", message, hint: "ודא ששרת ה-API רץ (uvicorn, פורט 8000)" };
  }
  return {
    title: "שגיאה בחיבור לשרת",
    message: "חלק מהמידע לא נטען. נסו שוב בעוד רגע.",
    hint: null,
    retryLabel: "נסו שוב",
  };
}
