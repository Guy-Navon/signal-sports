/**
 * M7-8 (#154) — NotificationsPanel helper tests (node environment, no DOM),
 * mirroring SchedulerPanel.test.jsx: the pure helpers behind the panel.
 */

import { describe, it, expect } from "vitest";
import {
  NOTIFICATION_STATUS_LABELS as STATUS_LABELS,
  manualReviewEvents,
  notificationsStateLabel,
} from "@/api/normalizers";

describe("STATUS_LABELS", () => {
  it("covers every outbox status with a Hebrew label", () => {
    for (const status of [
      "pending", "claimed", "sent", "failed_retryable",
      "failed_final", "unknown", "suppressed_watermark",
    ]) {
      expect(STATUS_LABELS[status].label).toBeTruthy();
    }
  });

  it("unknown is explicitly marked as never auto-resent", () => {
    expect(STATUS_LABELS.unknown.label).toContain("לא יישלח שוב");
  });
});

describe("manualReviewEvents", () => {
  it("selects unknown outcomes and stuck claims only", () => {
    const events = [
      { id: "a", status: "sent" },
      { id: "b", status: "unknown" },
      { id: "c", status: "claimed" },
      { id: "d", status: "pending" },
      { id: "e", status: "failed_final" },
    ];
    expect(manualReviewEvents(events).map((e) => e.id)).toEqual(["b", "c"]);
  });

  it("tolerates empty input", () => {
    expect(manualReviewEvents(undefined)).toEqual([]);
  });
});

describe("notificationsStateLabel", () => {
  it("disabled is calm", () => {
    expect(notificationsStateLabel({ enabled: false, configured: false }))
      .toEqual({ label: "כבוי", degraded: false });
  });

  it("enabled without configuration is a visible misconfiguration", () => {
    const s = notificationsStateLabel({ enabled: true, configured: false });
    expect(s.degraded).toBe(true);
    expect(s.label).toContain("חסרה תצורה");
  });

  it("unknown outcomes degrade the state", () => {
    const s = notificationsStateLabel({
      enabled: true, configured: true, unknown: 1,
      consecutive_delivery_failures: 0,
    });
    expect(s.degraded).toBe(true);
  });

  it("healthy active state", () => {
    const s = notificationsStateLabel({
      enabled: true, configured: true, unknown: 0,
      consecutive_delivery_failures: 0,
    });
    expect(s).toEqual({ label: "פעיל", degraded: false });
  });
});
