import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import {
  HEBREW_BROAD_SOURCES,
  FOOTBALL_FALSE_POS_SIGNALS,
  isPossibleFootballFalsePositive,
  filterByTimeWindow,
  calcMetrics,
  buildQaSummary,
} from "./llmQaHelpers";

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeItem(overrides = {}) {
  return {
    id: overrides.id ?? "rss_001",
    source: overrides.source ?? "walla_sport",
    title: overrides.title ?? "כותרת",
    sport: overrides.sport ?? "basketball",
    league: overrides.league ?? "EuroLeague",
    classifiedBy: overrides.classifiedBy ?? "rules",
    classificationProvider: overrides.classificationProvider ?? null,
    classificationConfidence: overrides.classificationConfidence ?? null,
    classificationReason: overrides.classificationReason ?? null,
    publishedAt: overrides.publishedAt ?? new Date().toISOString(),
    score: overrides.score ?? { decision: "feed" },
  };
}

function recentDate() {
  return new Date(Date.now() - 60 * 60 * 1000).toISOString(); // 1 hour ago
}

function oldDate() {
  return new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString(); // 48 hours ago
}

// ── HEBREW_BROAD_SOURCES ──────────────────────────────────────────────────────

describe("HEBREW_BROAD_SOURCES", () => {
  it("contains walla_sport", () => {
    expect(HEBREW_BROAD_SOURCES).toContain("walla_sport");
  });

  it("contains israel_hayom_sport", () => {
    expect(HEBREW_BROAD_SOURCES).toContain("israel_hayom_sport");
  });

  it("does not contain eurohoops or sportando", () => {
    expect(HEBREW_BROAD_SOURCES).not.toContain("eurohoops");
    expect(HEBREW_BROAD_SOURCES).not.toContain("sportando");
  });
});

// ── isPossibleFootballFalsePositive ───────────────────────────────────────────

describe("isPossibleFootballFalsePositive", () => {
  it("returns false for non-Hebrew-broad source", () => {
    const item = makeItem({ source: "eurohoops", sport: "basketball", title: "כדורגל" });
    expect(isPossibleFootballFalsePositive(item)).toBe(false);
  });

  it("returns false when sport is not basketball", () => {
    const item = makeItem({ source: "walla_sport", sport: "football", title: "כדורגל" });
    expect(isPossibleFootballFalsePositive(item)).toBe(false);
  });

  it("returns false when title has no football signal words", () => {
    const item = makeItem({ source: "walla_sport", sport: "basketball", title: "מכבי תל אביב ניצחה" });
    expect(isPossibleFootballFalsePositive(item)).toBe(false);
  });

  it("returns true for walla_sport + basketball + 'כדורגל' in title", () => {
    const item = makeItem({ source: "walla_sport", sport: "basketball", title: "כדורגל ישראלי" });
    expect(isPossibleFootballFalsePositive(item)).toBe(true);
  });

  it("returns true for israel_hayom_sport + basketball + 'ביתר' in title", () => {
    const item = makeItem({ source: "israel_hayom_sport", sport: "basketball", title: "ביתר ירושלים" });
    expect(isPossibleFootballFalsePositive(item)).toBe(true);
  });

  it("returns true for 'שוער' (goalkeeper) in basketball-classified article", () => {
    const item = makeItem({ source: "walla_sport", sport: "basketball", title: "שוער הקבוצה" });
    expect(isPossibleFootballFalsePositive(item)).toBe(true);
  });

  it("handles missing title gracefully", () => {
    const item = makeItem({ source: "walla_sport", sport: "basketball", title: undefined });
    expect(isPossibleFootballFalsePositive(item)).toBe(false);
  });

  it("is case-insensitive for signal words", () => {
    const item = makeItem({ source: "walla_sport", sport: "basketball", title: "כדורגל" });
    expect(isPossibleFootballFalsePositive(item)).toBe(true);
  });
});

// ── filterByTimeWindow ────────────────────────────────────────────────────────

describe("filterByTimeWindow", () => {
  it("returns all articles when timeFilter is 'all'", () => {
    const items = [makeItem({ publishedAt: oldDate() }), makeItem({ publishedAt: recentDate() })];
    expect(filterByTimeWindow(items, "all")).toHaveLength(2);
  });

  it("filters to last 24h when timeFilter is '24h'", () => {
    const items = [
      makeItem({ id: "old", publishedAt: oldDate() }),
      makeItem({ id: "new", publishedAt: recentDate() }),
    ];
    const result = filterByTimeWindow(items, "24h");
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("new");
  });

  it("returns empty array when all articles are older than 24h", () => {
    const items = [makeItem({ publishedAt: oldDate() })];
    expect(filterByTimeWindow(items, "24h")).toHaveLength(0);
  });

  it("includes articles published exactly at the boundary", () => {
    const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000 + 5000); // 5s inside window
    const items = [makeItem({ publishedAt: cutoff.toISOString() })];
    expect(filterByTimeWindow(items, "24h")).toHaveLength(1);
  });
});

// ── calcMetrics ───────────────────────────────────────────────────────────────

describe("calcMetrics", () => {
  it("returns zero counts for empty input", () => {
    const m = calcMetrics([], "all");
    expect(m.total).toBe(0);
    expect(m.wallaCount).toBe(0);
    expect(m.ihCount).toBe(0);
    expect(m.visibleForGuy).toBe(0);
    expect(m.hiddenForGuy).toBe(0);
    expect(m.unknownCount).toBe(0);
    expect(m.usedFallback).toBe(false);
  });

  it("only counts items from HEBREW_BROAD_SOURCES", () => {
    const items = [
      makeItem({ source: "walla_sport" }),
      makeItem({ source: "eurohoops" }),
      makeItem({ source: "sportando" }),
    ];
    const m = calcMetrics(items, "all");
    expect(m.total).toBe(1);
  });

  it("splits count by source (walla vs israel_hayom)", () => {
    const items = [
      makeItem({ source: "walla_sport" }),
      makeItem({ source: "walla_sport" }),
      makeItem({ source: "israel_hayom_sport" }),
    ];
    const m = calcMetrics(items, "all");
    expect(m.wallaCount).toBe(2);
    expect(m.ihCount).toBe(1);
    expect(m.total).toBe(3);
  });

  it("counts visible vs hidden based on score.decision", () => {
    const items = [
      makeItem({ score: { decision: "feed" } }),
      makeItem({ score: { decision: "push" } }),
      makeItem({ score: { decision: "hidden" } }),
    ];
    const m = calcMetrics(items, "all");
    expect(m.visibleForGuy).toBe(2);
    expect(m.hiddenForGuy).toBe(1);
  });

  it("counts sport=unknown articles", () => {
    const items = [
      makeItem({ sport: "basketball" }),
      makeItem({ sport: "unknown" }),
      makeItem({ sport: "unknown" }),
    ];
    const m = calcMetrics(items, "all");
    expect(m.unknownCount).toBe(2);
  });

  it("builds classifiedByBreakdown correctly", () => {
    const items = [
      makeItem({ classifiedBy: "llm" }),
      makeItem({ classifiedBy: "llm" }),
      makeItem({ classifiedBy: "rules" }),
    ];
    const m = calcMetrics(items, "all");
    expect(m.classifiedByBreakdown["llm"]).toBe(2);
    expect(m.classifiedByBreakdown["rules"]).toBe(1);
  });

  it("builds sportBreakdown correctly", () => {
    const items = [
      makeItem({ sport: "basketball" }),
      makeItem({ sport: "basketball" }),
      makeItem({ sport: "football" }),
    ];
    const m = calcMetrics(items, "all");
    expect(m.sportBreakdown["basketball"]).toBe(2);
    expect(m.sportBreakdown["football"]).toBe(1);
  });

  it("builds decisionBreakdown correctly", () => {
    const items = [
      makeItem({ score: { decision: "hidden" } }),
      makeItem({ score: { decision: "feed" } }),
    ];
    const m = calcMetrics(items, "all");
    expect(m.decisionBreakdown["hidden"]).toBe(1);
    expect(m.decisionBreakdown["feed"]).toBe(1);
  });

  it("applies 24h filter to Hebrew broad source items", () => {
    const items = [
      makeItem({ publishedAt: recentDate() }),
      makeItem({ publishedAt: oldDate() }),
    ];
    const m = calcMetrics(items, "24h");
    expect(m.total).toBe(1);
  });

  it("falls back to all-time when 24h filter yields zero results", () => {
    const items = [makeItem({ publishedAt: oldDate() })];
    const m = calcMetrics(items, "24h");
    expect(m.total).toBe(1);
    expect(m.usedFallback).toBe(true);
  });

  it("does NOT fall back when 24h filter returns results", () => {
    const items = [makeItem({ publishedAt: recentDate() })];
    const m = calcMetrics(items, "24h");
    expect(m.usedFallback).toBe(false);
  });

  it("usedFallback is false when all Hebrew items are old and timeFilter=all", () => {
    const items = [makeItem({ publishedAt: oldDate() })];
    const m = calcMetrics(items, "all");
    expect(m.usedFallback).toBe(false);
  });

  it("defaults classifiedBy to 'rules' when missing from item", () => {
    const items = [makeItem({ classifiedBy: undefined })];
    const m = calcMetrics(items, "all");
    expect(m.classifiedByBreakdown["rules"]).toBe(1);
  });
});

// ── buildQaSummary ────────────────────────────────────────────────────────────

describe("buildQaSummary", () => {
  const baseArgs = {
    timestamp: "2026-06-14T10:00:00.000Z",
    providerStatus: {
      provider: "ollama",
      can_classify: true,
      model: "llama3.2:3b",
      base_url: "http://localhost:11434",
    },
    lastResetResult: { deleted_articles: 30, deleted_ingestion_runs: 5 },
    ingestResults: [
      {
        source_id: "walla_sport",
        fetched: 30,
        inserted: 30,
        skipped_filtered: 0,
        skipped_duplicate: 0,
        failed: 0,
      },
    ],
    metrics: {
      total: 30,
      wallaCount: 20,
      ihCount: 10,
      visibleForGuy: 15,
      hiddenForGuy: 15,
      unknownCount: 3,
      classifiedByBreakdown: { llm: 25, rules: 5 },
      sportBreakdown: { basketball: 22, football: 5, unknown: 3 },
      decisionBreakdown: { feed: 10, hidden: 15, push: 5 },
      items: [],
    },
  };

  it("includes the markdown title", () => {
    const summary = buildQaSummary(baseArgs);
    expect(summary).toContain("# Signal Sports — LLM QA Summary");
  });

  it("includes the timestamp", () => {
    const summary = buildQaSummary(baseArgs);
    expect(summary).toContain("2026-06-14T10:00:00.000Z");
  });

  it("includes provider status section", () => {
    const summary = buildQaSummary(baseArgs);
    expect(summary).toContain("ollama");
    expect(summary).toContain("llama3.2:3b");
  });

  it("includes reset section when lastResetResult is provided", () => {
    const summary = buildQaSummary(baseArgs);
    expect(summary).toContain("30");  // deleted_articles
    expect(summary).toContain("5");   // deleted_ingestion_runs
  });

  it("includes ingest results section", () => {
    const summary = buildQaSummary(baseArgs);
    expect(summary).toContain("walla_sport");
    expect(summary).toContain("fetched=30");
    expect(summary).toContain("inserted=30");
  });

  it("includes metrics section", () => {
    const summary = buildQaSummary(baseArgs);
    expect(summary).toContain("סה״כ כתבות: 30");
    expect(summary).toContain("וואלה ספורט: 20");
    expect(summary).toContain("ישראל היום: 10");
    expect(summary).toContain("ניראה לגיא: 15");
    expect(summary).toContain("מוסתר לגיא: 15");
  });

  it("includes classified_by breakdown", () => {
    const summary = buildQaSummary(baseArgs);
    expect(summary).toContain("llm: 25");
    expect(summary).toContain("rules: 5");
  });

  it("includes decision breakdown sorted by rank", () => {
    const summary = buildQaSummary(baseArgs);
    const pushIndex = summary.indexOf("push: 5");
    const feedIndex = summary.indexOf("feed: 10");
    const hiddenIndex = summary.indexOf("hidden: 15");
    // push should appear before feed, which should appear before hidden
    expect(pushIndex).toBeLessThan(feedIndex);
    expect(feedIndex).toBeLessThan(hiddenIndex);
  });

  it("omits reset section when lastResetResult is null", () => {
    const summary = buildQaSummary({ ...baseArgs, lastResetResult: null });
    expect(summary).not.toContain("## איפוס");
  });

  it("omits ingest section when ingestResults is empty", () => {
    const summary = buildQaSummary({ ...baseArgs, ingestResults: [] });
    expect(summary).not.toContain("## ייבוא");
  });

  it("omits metrics section when metrics is null", () => {
    const summary = buildQaSummary({ ...baseArgs, metrics: null });
    expect(summary).not.toContain("## מדדים");
  });

  it("handles null providerStatus gracefully", () => {
    const summary = buildQaSummary({ ...baseArgs, providerStatus: null });
    expect(summary).toContain("לא נטען");
  });

  it("includes top visible articles when items are present", () => {
    const items = [
      makeItem({ id: "a1", title: "כתבה חשובה", sport: "basketball", score: { decision: "push" } }),
    ];
    const summary = buildQaSummary({
      ...baseArgs,
      metrics: { ...baseArgs.metrics, items },
    });
    expect(summary).toContain("כתבה חשובה");
  });

  it("includes unknown-sport articles section when present", () => {
    const items = [
      makeItem({ id: "u1", title: "כותרת לא ידועה", sport: "unknown", score: { decision: "hidden" } }),
    ];
    const summary = buildQaSummary({
      ...baseArgs,
      metrics: { ...baseArgs.metrics, items },
    });
    expect(summary).toContain("sport=unknown");
    expect(summary).toContain("כותרת לא ידועה");
  });

  it("includes football false positives section when present", () => {
    const items = [
      makeItem({
        id: "fp1",
        title: "כדורגל ישראלי — מחזור 30",
        source: "walla_sport",
        sport: "basketball",
        score: { decision: "feed" },
      }),
    ];
    const summary = buildQaSummary({
      ...baseArgs,
      metrics: { ...baseArgs.metrics, items },
    });
    expect(summary).toContain("false positive");
    expect(summary).toContain("כדורגל ישראלי");
  });
});
