import { describe, expect, it, vi } from "vitest";
import {
  DEMO_STALE_AFTER_MINUTES,
  demoBanner,
  demoDecisionCounts,
  demoResultsView,
  scoresOnlyGame,
  tabFromHash,
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
const RESULT = {
  id: "game_1", competition_id: "comp:euroleague", competition_he: "יורוליג",
  status: "final", start_time: "2026-11-11T08:00:00Z", winner: "home",
  home: { name: "מכבי תל אביב", score: 90, is_winner: true },
  away: { name: "ריאל מדריד", score: 85, is_winner: false },
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
  it("fetches only its three static files, uncached, and returns prepared items and normalized results", async () => {
    const { impl, calls } = fakeFetch({
      "/demo-data/feed.json": [ITEM, { ...ITEM, decision: "hidden", article: { ...ITEM.article, id: "rss_h" } }],
      "/demo-data/meta.json": META,
      "/demo-data/results.json": { has_preferences: true, games: [RESULT] },
    });

    const snapshot = await loadDemoSnapshot(impl, "/");

    expect(calls.map((c) => c.url).sort()).toEqual([
      "/demo-data/feed.json", "/demo-data/meta.json", "/demo-data/results.json",
    ]);
    expect(calls.every((c) => c.init?.cache === "no-store")).toBe(true);
    expect(snapshot.meta).toEqual(META);
    // Same normalization the real app applies; hidden items never reach the view.
    expect(snapshot.items.map((i) => i.id)).toEqual(["rss_1"]);
    expect(snapshot.items[0].score.reasonHe).toBe(ITEM.reason_he);
    expect(snapshot.items[0].sourceDisplayName).toBe("וואלה ספורט");
    expect(snapshot.items[0].type).toBe("article");
    expect(snapshot.results).toMatchObject([{
      id: "game_1", competitionId: "comp:euroleague", competitionHe: "יורוליג",
      startTime: RESULT.start_time, home: { name: "מכבי תל אביב", score: 90, isWinner: true },
    }]);
  });

  it("honours a non-root base path", async () => {
    const { impl, calls } = fakeFetch({
      "/sub/demo-data/feed.json": [],
      "/sub/demo-data/meta.json": { ...META, item_count: 0 },
      "/sub/demo-data/results.json": { has_preferences: true, games: [RESULT] },
    });
    const snapshot = await loadDemoSnapshot(impl, "/sub/");
    expect(snapshot.items).toEqual([]);
    expect(snapshot.results).toHaveLength(1);
    expect(calls).toHaveLength(3);
  });

  it.each([undefined, null, "broken", {}, { games: "broken" }, { games: [null] }])(
    "ignores missing or malformed optional results (%j)", async (results) => {
      const { impl } = fakeFetch({
        "/demo-data/feed.json": [ITEM], "/demo-data/meta.json": META,
        "/demo-data/results.json": results,
      });
      const snapshot = await loadDemoSnapshot(impl);
      expect(snapshot.items).toHaveLength(1);
      expect(snapshot.results).toEqual([]);
    },
  );

  it.each(["network", "json"])("ignores an optional results %s failure", async (failure) => {
    const { impl } = fakeFetch({ "/demo-data/feed.json": [ITEM], "/demo-data/meta.json": META });
    const fetchImpl = async (url, init) => {
      if (url.endsWith("results.json")) {
        if (failure === "network") throw new Error("offline");
        return { ok: true, status: 200, json: async () => { throw new SyntaxError("invalid JSON"); } };
      }
      return impl(url, init);
    };
    expect((await loadDemoSnapshot(fetchImpl)).results).toEqual([]);
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

const wire = (id, extra = {}) => ({
  id, competitionId: "comp:nba", competitionHe: "NBA", sport: "basketball", status: "final",
  startTime: "2026-11-14T03:00:00Z", localDate: "2026-11-14", winner: "home", relevanceReason: "",
  home: { id: "team:a", name: "A", score: 100, isWinner: true },
  away: { id: "team:b", name: "B", score: 90, isWinner: false }, ...extra,
});
const NOW = new Date("2026-11-14T12:00:00Z");

describe("tabFromHash", () => {
  it("is results only for #results; the feed otherwise", () => {
    expect(tabFromHash("#results")).toBe("results");
    for (const hash of ["", "#", "#feed", "#results2", undefined]) expect(tabFromHash(hash)).toBe("feed");
  });
});

describe("scoresOnlyGame", () => {
  it("drops leaders, chosen lines, ranks, venue, attendance and detail even if present", () => {
    const rich = { ...wire("g"), leaders: [{ name: "X", value: 30 }], chosenPlayerLines: [{ name: "Y" }], venue: "Arena",
      attendance: 100, detailAvailable: true, home: { ...wire("g").home, rank: 3 } };
    const game = scoresOnlyGame(rich);
    expect(game.leaders).toEqual([]);
    expect(game.chosenPlayerLines).toEqual([]);
    expect(game.detailAvailable).toBe(false);
    expect(game.home.rank).toBeNull();
    expect(game).not.toHaveProperty("venue");
    expect(game).not.toHaveProperty("attendance");
    expect(game.home.score).toBe(100);
  });
  it("copes with absent optional fields", () => {
    expect(() => scoresOnlyGame({ id: "g", status: "final", home: {}, away: undefined })).not.toThrow();
  });
});

describe("demoResultsView", () => {
  it("picks tiles only from followed_team reasons, newest first, at most four", () => {
    const games = [
      ...[1, 2, 3, 4, 5].map((n) => wire(`f${n}`, { relevanceReason: "followed_team:team:a", startTime: `2026-11-14T0${n}:00:00Z` })),
      wire("plain", { relevanceReason: "followed_competition:comp:nba", startTime: "2026-11-14T09:00:00Z" }),
    ].map(scoresOnlyGame);
    const view = demoResultsView(games, NOW);
    expect(view.tiles.map((t) => t.game.id)).toEqual(["f5", "f4", "f3", "f2"]);
    expect(view.tiles[0].verdict.kind).toBe("win");
    expect(view.tiles.every((t) => t.chosen === null)).toBe(true);
  });
  it("shows a loss verdict from the followed side", () => {
    const [tile] = demoResultsView([scoresOnlyGame(wire("g", { winner: "away", relevanceReason: "followed_team:team:a" }))], NOW).tiles;
    expect(tile.verdict.kind).toBe("loss");
  });
  it("has no tiles when nothing is followed, and stays ready", () => {
    const view = demoResultsView([scoresOnlyGame(wire("g"))], NOW);
    expect(view.state).toBe("ready");
    expect(view.tiles).toEqual([]);
    expect(view.days).toHaveLength(1);
  });
  it("is empty with no games or no finals", () => {
    expect(demoResultsView([], NOW).state).toBe("empty");
    expect(demoResultsView([scoresOnlyGame(wire("g", { status: "scheduled" }))], NOW).state).toBe("empty");
  });
  it("summarises finals of the last 48 hours from the data", () => {
    const view = demoResultsView([scoresOnlyGame(wire("a")), scoresOnlyGame(wire("b"))], NOW);
    expect(view.summary).toEqual([{ n: 2, label: "משחקים ב-48 השעות האחרונות" }]);
  });
});
