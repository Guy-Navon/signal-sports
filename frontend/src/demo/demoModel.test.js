import { describe, expect, it, vi } from "vitest";
import {
  DEMO_STALE_AFTER_MINUTES,
  demoBanner,
  demoDecisionCounts,
  loadDemoSnapshot,
} from "./demoModel";

// One item in the exporter's wire shape (backend/app/ops/demo_snapshot.py).
const ITEM = {
  decision: "high_feed",
  reason_he: "מכבי תל אביב (כדורסל) ברשימת המעקב שלך",
  article: {
    id: "rss_1",
    source: "walla_sport",
    source_display_name: "וואלה ספורט",
    url: "https://sports.walla.co.il/item/1",
    title: "מכבי תל אביב צפויה לצרף גארד",
    original_title: null,
    translated_title: null,
    language: "he",
    published_at: "2026-11-09T06:39:00Z",
    sport: "basketball",
    league: "EuroLeague",
    entities: ["Maccabi Tel Aviv Basketball"],
    event_type: "negotiation",
    importance: "high",
    tags: [],
    cluster_id: null,
    subtitle: null,
  },
  cluster: null,
};
const META = {
  schema_version: 1,
  generated_at: "2026-11-11T10:00:00+00:00",
  last_successful_cycle_at: "2026-11-11T09:50:00+00:00",
  item_count: 1,
};

function fakeFetch(responses) {
  const calls = [];
  const impl = vi.fn(async (url, init) => {
    calls.push({ url, init });
    const body = responses[url];
    if (body === undefined) return { ok: false, status: 404, json: async () => ({}) };
    return { ok: true, status: 200, json: async () => body };
  });
  return { impl, calls };
}

describe("loadDemoSnapshot", () => {
  it("fetches only its two static files, uncached, and returns orbit items", async () => {
    const { impl, calls } = fakeFetch({
      "/demo-data/feed.json": [ITEM, { ...ITEM, decision: "hidden", article: { ...ITEM.article, id: "rss_h" } }],
      "/demo-data/meta.json": META,
    });

    const snapshot = await loadDemoSnapshot(impl, "/");

    expect(calls.map((c) => c.url).sort()).toEqual(["/demo-data/feed.json", "/demo-data/meta.json"]);
    expect(calls.every((c) => c.init?.cache === "no-store")).toBe(true);
    expect(snapshot.meta).toEqual(META);
    // Same normalization the real app applies; hidden items never reach the view.
    expect(snapshot.items.map((i) => i.id)).toEqual(["rss_1"]);
    expect(snapshot.items[0].score.reasonHe).toBe(ITEM.reason_he);
    expect(snapshot.items[0].sourceDisplayName).toBe("וואלה ספורט");
    expect(snapshot.items[0].type).toBe("article");
  });

  it("honours a non-root base path", async () => {
    const { impl, calls } = fakeFetch({
      "/sub/demo-data/feed.json": [],
      "/sub/demo-data/meta.json": { ...META, item_count: 0 },
    });
    const snapshot = await loadDemoSnapshot(impl, "/sub/");
    expect(snapshot.items).toEqual([]);
    expect(calls).toHaveLength(2);
  });

  it("fails when a file is missing, so the page shows its error state", async () => {
    const { impl } = fakeFetch({ "/demo-data/meta.json": META });
    await expect(loadDemoSnapshot(impl, "/")).rejects.toThrow(/404/);
  });

  it("fails on a malformed feed instead of rendering garbage", async () => {
    const { impl } = fakeFetch({
      "/demo-data/feed.json": { not: "a list" },
      "/demo-data/meta.json": META,
    });
    await expect(loadDemoSnapshot(impl, "/")).rejects.toThrow(/feed/);
  });
});

describe("demoBanner", () => {
  const now = Date.parse("2026-11-11T10:02:00+00:00");

  it("says how long ago the pipeline last refreshed the feed", () => {
    expect(demoBanner(META, now)).toEqual({ updated: "עודכן לפני 12 דק׳", stale: false, warning: null });
  });

  it("turns stale after three hours and says so plainly", () => {
    const old = { ...META, last_successful_cycle_at: "2026-11-11T06:30:00+00:00" };
    const view = demoBanner(old, now);
    expect(DEMO_STALE_AFTER_MINUTES).toBe(180);
    expect(view.stale).toBe(true);
    expect(view.updated).toBe("עודכן לפני 3 שע׳");
    expect(view.warning).toBe("הנתונים בהדגמה לא התעדכנו כבר כמה שעות");
  });

  it("falls back to the export time when no cycle time is known", () => {
    const view = demoBanner({ ...META, last_successful_cycle_at: null }, now);
    expect(view.updated).toBe("עודכן לפני 2 דק׳");
    expect(view.stale).toBe(false);
  });

  it("stays honest without any usable time", () => {
    expect(demoBanner({ generated_at: "garbage" }, now)).toEqual({
      updated: "זמן העדכון לא ידוע", stale: true, warning: "הנתונים בהדגמה לא התעדכנו כבר כמה שעות",
    });
    expect(demoBanner(null, now).stale).toBe(true);
  });
});

describe("demoDecisionCounts", () => {
  it("counts visible levels and ignores anything else", () => {
    const items = [
      { score: { decision: "push" } },
      { score: { decision: "feed" } },
      { score: { decision: "feed" } },
      { score: { decision: "hidden" } },
      {},
    ];
    expect(demoDecisionCounts(items)).toEqual({ push: 1, high_feed: 0, feed: 2, low_feed: 0 });
  });
});
