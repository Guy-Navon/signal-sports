/**
 * PR 13 — SchedulerStatusPanel helper tests (node environment, no DOM).
 *
 * Mirrors GatingBenchmarkPanel.test.jsx: tests the pure display helpers and
 * normalizers that back the panel, plus the busy-error detection used to
 * disable the "הרץ עכשיו" button.
 */

import { describe, it, expect } from "vitest";
import {
  normalizeSchedulerStatusFromApi,
  normalizeSourceHealthFromApi,
  freshnessBadge,
  sourceTypeLabel,
} from "@/api/normalizers";
import { isIngestionBusyError } from "@/api/client";

// ── freshnessBadge ────────────────────────────────────────────────────────────

describe("freshnessBadge", () => {
  it.each([
    ["healthy", "תקין"],
    ["stale", "מיושן"],
    ["never_run", "לא רץ עדיין"],
    ["disabled", "כבוי"],
    ["error", "שגיאה"],
  ])("maps %s to Hebrew label %s", (freshness, label) => {
    expect(freshnessBadge(freshness).label).toBe(label);
  });

  it("returns colorClass for every known freshness", () => {
    for (const f of ["healthy", "stale", "never_run", "disabled", "error"]) {
      expect(freshnessBadge(f).colorClass).toBeTruthy();
    }
  });

  it("uses emerald for healthy and red for error", () => {
    expect(freshnessBadge("healthy").colorClass).toContain("emerald");
    expect(freshnessBadge("error").colorClass).toContain("red");
  });

  it("falls back to never_run style for unknown values", () => {
    expect(freshnessBadge("nonsense").label).toBe("לא רץ עדיין");
    expect(freshnessBadge(undefined).label).toBe("לא רץ עדיין");
  });
});

// ── sourceTypeLabel ───────────────────────────────────────────────────────────

describe("sourceTypeLabel", () => {
  it("labels html_scrape as Scraping", () => {
    expect(sourceTypeLabel("html_scrape")).toBe("Scraping");
  });

  it("labels rss and unknown types as RSS", () => {
    expect(sourceTypeLabel("rss")).toBe("RSS");
    expect(sourceTypeLabel(undefined)).toBe("RSS");
  });
});

// ── normalizeSchedulerStatusFromApi ──────────────────────────────────────────

describe("normalizeSchedulerStatusFromApi", () => {
  it("converts snake_case to camelCase", () => {
    const s = normalizeSchedulerStatusFromApi({
      enabled: true,
      running: true,
      worker_running: true,
      automatic_ingestion_active: true,
      interval_minutes: 10,
      next_run_at: "2026-07-01T12:00:00+00:00",
      last_started_at: "2026-07-01T11:50:00+00:00",
      last_finished_at: "2026-07-01T11:51:00+00:00",
      last_status: "ok",
      last_error: null,
      active_run: { trigger: "scheduled", started_at: "2026-07-01T11:50:00+00:00" },
      last_result_summary: [{ source_id: "walla_sport", inserted: 3 }],
    });
    expect(s.enabled).toBe(true);
    expect(s.workerRunning).toBe(true);
    expect(s.automaticIngestionActive).toBe(true);
    expect(s.intervalMinutes).toBe(10);
    expect(s.nextRunAt).toBe("2026-07-01T12:00:00+00:00");
    expect(s.lastStatus).toBe("ok");
    expect(s.activeRun.trigger).toBe("scheduled");
    expect(s.lastResultSummary).toHaveLength(1);
  });

  it("tolerates nulls and missing fields", () => {
    const s = normalizeSchedulerStatusFromApi({});
    expect(s.enabled).toBe(false);
    expect(s.running).toBe(false);
    expect(s.workerRunning).toBe(false);
    expect(s.automaticIngestionActive).toBe(false);
    expect(s.intervalMinutes).toBe(15);
    expect(s.nextRunAt).toBeNull();
    expect(s.lastStatus).toBe("never_run");
    expect(s.activeRun).toBeNull();
    expect(s.lastResultSummary).toBeNull();
  });

  it("surfaces automatic ingestion active even when the API env flag is off", () => {
    // The two-process topology: worker alive, API's SCHEDULER_ENABLED false.
    const s = normalizeSchedulerStatusFromApi({
      enabled: false,
      running: true,
      worker_running: true,
      automatic_ingestion_active: true,
    });
    expect(s.enabled).toBe(false);
    expect(s.automaticIngestionActive).toBe(true);
  });

  it("derives automaticIngestionActive from worker_running when the field is absent", () => {
    const s = normalizeSchedulerStatusFromApi({ enabled: false, worker_running: true });
    expect(s.automaticIngestionActive).toBe(true);
  });
});

// ── normalizeSourceHealthFromApi ─────────────────────────────────────────────

describe("normalizeSourceHealthFromApi", () => {
  it("converts a full health record", () => {
    const h = normalizeSourceHealthFromApi({
      source_id: "sport5_sport",
      display_name: "ערוץ הספורט",
      enabled: false,
      source_type: "html_scrape",
      is_pilot: true,
      freshness: "disabled",
      last_run_at: "2026-07-01T10:00:00+00:00",
      last_status: "ok",
      last_fetched_count: 5,
      last_inserted_count: 5,
      last_failed_count: 0,
      last_skipped_duplicate_count: 0,
      consecutive_failures: 0,
      last_error_message: null,
    });
    expect(h.sourceId).toBe("sport5_sport");
    expect(h.displayName).toBe("ערוץ הספורט");
    expect(h.sourceType).toBe("html_scrape");
    expect(h.isPilot).toBe(true);
    expect(h.freshness).toBe("disabled");
    expect(h.lastFetchedCount).toBe(5);
  });

  it("tolerates never_run records with null counts", () => {
    const h = normalizeSourceHealthFromApi({
      source_id: "walla_sport",
      display_name: "וואלה ספורט",
      enabled: true,
      freshness: "never_run",
    });
    expect(h.lastRunAt).toBeNull();
    expect(h.lastFetchedCount).toBeNull();
    expect(h.consecutiveFailures).toBe(0);
    expect(h.isPilot).toBe(false);
    expect(h.sourceType).toBe("rss");
  });
});

// ── Busy-error detection (drives the disabled run-now button) ────────────────

describe("busy error handling", () => {
  it("409 from run-now is detected as busy", () => {
    const err = new Error(
      'API POST /api/ingest/scheduler/run-now failed (409): {"error":"ingestion_already_running","message":"ייבוא פעיל כרגע"}'
    );
    expect(isIngestionBusyError(err)).toBe(true);
  });

  it("regular errors are not busy", () => {
    expect(isIngestionBusyError(new Error("Cannot reach backend"))).toBe(false);
  });
});
