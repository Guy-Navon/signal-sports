// Debug's compare tab scores mock articles, so it only means something in local
// (demo) mode. In backend mode it shows this line and loads no demo code (#199).
export const COMPARE_DEMO_ONLY_MESSAGE = "השוואת פרופילים זמינה רק במצב הדגמה.";

export function showsDemoComparison(isBackendMode) {
  return !isBackendMode;
}
