// Feed freshness (#249): when was the feed last refreshed, and is automatic
// ingestion running? Pure, node-tested. The server owns both verdicts
// (GET /api/me/feed/freshness, computed like /api/scheduler/health); this
// module only turns them into one quiet Hebrew line plus an optional warning.

// Six scheduler intervals (5 min each). A worker that claims to run but has
// not completed a successful cycle for longer than this is stuck.
export const FEED_STALE_AFTER_MINUTES = 30;

const WARNING_STOPPED = "הייבוא האוטומטי לא רץ — הפיד לא מתעדכן";
const WARNING_STUCK = "הפיד לא התעדכן מעל חצי שעה — הייבוא נתקע";

export function formatUpdatedAgo(minutes) {
  const m = Math.max(0, Math.floor(minutes));
  if (m < 1) return "עודכן הרגע";
  if (m === 1) return "עודכן לפני דקה";
  if (m < 60) return `עודכן לפני ${m} דק׳`;
  const h = Math.floor(m / 60);
  if (h === 1) return "עודכן לפני שעה";
  if (h < 24) return `עודכן לפני ${h} שע׳`;
  const d = Math.floor(h / 24);
  if (d === 1) return "עודכן לפני יום";
  return `עודכן לפני ${d} ימים`;
}

/**
 * @param {{last_successful_cycle_at: string|null, worker_running: boolean}|null|undefined} freshness
 * @param {number} nowMs
 * @returns {{label: string, warning: string|null}|null} null = render nothing
 */
export function feedFreshnessView(freshness, nowMs) {
  if (!freshness) return null;
  const parsed = freshness.last_successful_cycle_at
    ? Date.parse(freshness.last_successful_cycle_at)
    : NaN;
  const hasSuccess = Number.isFinite(parsed);
  const ageMinutes = hasSuccess ? Math.max(0, (nowMs - parsed) / 60_000) : null;

  let warning = null;
  if (!freshness.worker_running) {
    warning = WARNING_STOPPED;
  } else if (ageMinutes === null || ageMinutes > FEED_STALE_AFTER_MINUTES) {
    warning = WARNING_STUCK;
  }

  return {
    label: hasSuccess ? formatUpdatedAgo(ageMinutes) : "הפיד עוד לא עודכן",
    warning,
  };
}
