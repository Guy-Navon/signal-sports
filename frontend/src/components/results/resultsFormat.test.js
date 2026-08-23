import { describe, it, expect } from "vitest";
import { jerusalemDayKey, formatGameTime, formatDayHeading } from "./resultsFormat";

describe("jerusalemDayKey", () => {
  it("returns the calendar day in Asia/Jerusalem", () => {
    // 02:00 UTC on Apr 10 is 05:00 Jerusalem (DST +3) → same day.
    expect(jerusalemDayKey("2026-04-10T02:00:00+00:00")).toBe("2026-04-10");
  });

  it("rolls a late-UTC time into the next Jerusalem day", () => {
    // 22:30 UTC Apr 9 → 01:30 Jerusalem Apr 10 (DST +3).
    expect(jerusalemDayKey("2026-04-09T22:30:00+00:00")).toBe("2026-04-10");
  });

  it("returns null for missing/invalid input", () => {
    expect(jerusalemDayKey(null)).toBeNull();
    expect(jerusalemDayKey("not-a-date")).toBeNull();
  });
});

describe("formatGameTime", () => {
  it("formats HH:mm in the app timezone", () => {
    expect(formatGameTime("2026-04-10T02:00:00+00:00")).toBe("05:00");
    expect(formatGameTime(null)).toBe("");
  });
});

describe("formatDayHeading", () => {
  const now = new Date("2026-04-10T09:00:00+00:00");

  it("labels today and yesterday relatively", () => {
    expect(formatDayHeading("2026-04-10", now)).toBe("היום");
    expect(formatDayHeading("2026-04-09", now)).toBe("אתמול");
  });

  it("renders an absolute Hebrew date for older days", () => {
    const label = formatDayHeading("2026-04-05", now);
    expect(label).toContain("2026");
    expect(label).not.toBe("היום");
    expect(label).not.toBe("אתמול");
  });

  it("handles the undated bucket", () => {
    expect(formatDayHeading(null)).toBe("ללא תאריך");
  });
});
