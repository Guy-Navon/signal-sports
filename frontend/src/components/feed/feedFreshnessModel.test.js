import { describe, expect, it } from "vitest";
import {
  FEED_STALE_AFTER_MINUTES,
  feedFreshnessView,
  formatUpdatedAgo,
} from "./feedFreshnessModel";

const NOW = Date.parse("2026-10-25T12:00:00Z");
const minutesAgo = (m) => new Date(NOW - m * 60_000).toISOString();

describe("formatUpdatedAgo", () => {
  it("speaks Hebrew at every scale", () => {
    expect(formatUpdatedAgo(0)).toBe("עודכן הרגע");
    expect(formatUpdatedAgo(0.6)).toBe("עודכן הרגע");
    expect(formatUpdatedAgo(1)).toBe("עודכן לפני דקה");
    expect(formatUpdatedAgo(4)).toBe("עודכן לפני 4 דק׳");
    expect(formatUpdatedAgo(59)).toBe("עודכן לפני 59 דק׳");
    expect(formatUpdatedAgo(60)).toBe("עודכן לפני שעה");
    expect(formatUpdatedAgo(150)).toBe("עודכן לפני 2 שע׳");
    expect(formatUpdatedAgo(24 * 60)).toBe("עודכן לפני יום");
    expect(formatUpdatedAgo(10 * 24 * 60)).toBe("עודכן לפני 10 ימים");
  });
});

describe("feedFreshnessView", () => {
  it("shows nothing until the signal has loaded (and in local mode)", () => {
    expect(feedFreshnessView(null, NOW)).toBeNull();
    expect(feedFreshnessView(undefined, NOW)).toBeNull();
  });

  it("is a quiet age line while the worker runs and the last success is recent", () => {
    const view = feedFreshnessView(
      { last_successful_cycle_at: minutesAgo(4), worker_running: true },
      NOW,
    );
    expect(view).toEqual({ label: "עודכן לפני 4 דק׳", warning: null });
  });

  it("warns plainly when automatic ingestion is not running", () => {
    const view = feedFreshnessView(
      { last_successful_cycle_at: minutesAgo(3), worker_running: false },
      NOW,
    );
    expect(view.label).toBe("עודכן לפני 3 דק׳");
    expect(view.warning).toBe("הייבוא האוטומטי לא רץ — הפיד לא מתעדכן");
  });

  it("warns when the worker claims to run but nothing succeeded for too long", () => {
    const atThreshold = feedFreshnessView(
      { last_successful_cycle_at: minutesAgo(FEED_STALE_AFTER_MINUTES), worker_running: true },
      NOW,
    );
    expect(atThreshold.warning).toBeNull();

    const past = feedFreshnessView(
      { last_successful_cycle_at: minutesAgo(FEED_STALE_AFTER_MINUTES + 1), worker_running: true },
      NOW,
    );
    expect(past.label).toBe("עודכן לפני 31 דק׳");
    expect(past.warning).toBe("הפיד לא התעדכן מעל חצי שעה — הייבוא נתקע");
  });

  it("never claims an age when no cycle has ever succeeded", () => {
    expect(
      feedFreshnessView({ last_successful_cycle_at: null, worker_running: true }, NOW),
    ).toEqual({ label: "הפיד עוד לא עודכן", warning: "הפיד לא התעדכן מעל חצי שעה — הייבוא נתקע" });
    expect(
      feedFreshnessView({ last_successful_cycle_at: null, worker_running: false }, NOW).warning,
    ).toBe("הייבוא האוטומטי לא רץ — הפיד לא מתעדכן");
  });

  it("treats an unparseable timestamp like a missing one", () => {
    const view = feedFreshnessView(
      { last_successful_cycle_at: "not-a-date", worker_running: true },
      NOW,
    );
    expect(view.label).toBe("הפיד עוד לא עודכן");
    expect(view.warning).not.toBeNull();
  });

  it("clamps a timestamp slightly in the future (clock skew) to 'just now'", () => {
    const view = feedFreshnessView(
      { last_successful_cycle_at: minutesAgo(-2), worker_running: true },
      NOW,
    );
    expect(view).toEqual({ label: "עודכן הרגע", warning: null });
  });
});
