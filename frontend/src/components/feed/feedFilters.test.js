import { describe, it, expect } from "vitest";
import {
  LEVEL_FILTER_IDS,
  TOPIC_CHIPS,
  getVisibleItems,
  itemMatchesFilter,
  filterFeedItems,
  leagueFilterId,
  toggleFilterSet,
  ALL_LEAGUES_ID,
  ALL_LEVELS_ID,
  activeLeagueIds,
  activeLevelIds,
  isVisibleItem,
  hasActiveFilters,
  importanceOptions,
  facetedLeagueCounts,
  visibleCount,
  sourceFilterId,
  activeSourceIds,
  facetedSourceCounts,
  sourceOptions,
  ALL_SOURCES_ID,
} from "./feedFilters";

const mk = (over = {}) => ({ score: { decision: "feed" }, ...over });

describe("source facets (#483)", () => {
  const items = [
    mk({ id: "p", source: "one", sourceDisplayName: "ONE", league: "NBA", score: { decision: "push" } }),
    mk({ id: "c", type: "cluster", league: "NBA", score: { decision: "high_feed" },
      sources: ["stale"], members: [
        { source: "one", sourceDisplayName: "ONE" },
        { source: "walla", sourceDisplayName: "וואלה" },
        { source: "walla", sourceDisplayName: "וואלה" },
        { source: "secret", decision: "hidden" },
      ] }),
    mk({ id: "e", source: "walla", sourceDisplayName: "וואלה", league: "EuroLeague" }),
    mk({ id: "n", source: "other", league: "NBA" }),
    mk({ id: "x", source: "secret", league: "NBA", score: { decision: "hidden" } }),
    mk({ id: "y", source: "secret", score: {} }),
  ];
  const ids = (active) => filterFeedItems(items, new Set(active)).map((item) => item.id);

  it("ANDs importance, leagues and sources; ORs values within each facet, keeping rank order", () => {
    expect(sourceFilterId("walla")).toBe("source:walla");
    expect(ids(["high_feed", "league:NBA", "source:walla"])).toEqual(["c"]);
    expect(ids(["league:NBA", "league:EuroLeague", "source:walla", "source:one"])).toEqual(["p", "c", "e"]);
    expect(ids(["league:EuroLeague", "source:one"])).toEqual([]);
    expect(ids(["source:other"])).toEqual(["n"]);
  });

  it("matches any visible member source, once per cluster, using the authoritative members", () => {
    expect(itemMatchesFilter(items[1], "source:walla")).toBe(true);
    expect(itemMatchesFilter(items[1], "source:stale")).toBe(false);
    expect(itemMatchesFilter(items[1], "source:secret")).toBe(false);
    expect(itemMatchesFilter(mk({ type: "cluster", sources: ["one", "walla"] }), "source:walla")).toBe(true);
    expect(facetedSourceCounts(items, new Set(["all"]))).toEqual(new Map([
      ["source:one", 2], ["source:walla", 2], ["source:other", 1],
    ]));
  });

  it("never passes hidden or decision-less stories, even for all or an empty set", () => {
    for (const active of [["all"], [], ["source:secret"], ["league:NBA"]]) {
      expect(ids(active)).not.toEqual(expect.arrayContaining(["x"]));
      expect(ids(active)).not.toEqual(expect.arrayContaining(["y"]));
    }
  });

  it("counts each facet under the other two, ignoring its own selections", () => {
    const active = new Set(["high_feed", "league:NBA", "source:walla"]);
    expect(facetedSourceCounts(items, active)).toEqual(new Map([["source:one", 1], ["source:walla", 1]]));
    expect(facetedLeagueCounts(items, new Set(["source:walla", "league:EuroLeague"])))
      .toEqual(new Map([["league:NBA", 1], ["league:EuroLeague", 1]]));
    expect(importanceOptions(items, active).map((o) => o.count)).toEqual([1, 0, 1, 0, 0]);
  });

  it("uses feed display names, stable order, and retains a selected zero-count source", () => {
    const active = new Set(["league:EuroLeague", "source:one"]);
    expect(sourceOptions(items, active)).toEqual([
      { id: "source:one", label: "ONE", count: 0 },
      { id: "source:walla", label: "וואלה", count: 1 },
    ]);
  });

  it("toggles and clears sources independently, with no persistence", () => {
    const active = new Set(["feed", "league:NBA", "source:one", "source:walla"]);
    expect(activeSourceIds(active)).toEqual(["source:one", "source:walla"]);
    expect([...toggleFilterSet(active, ALL_SOURCES_ID)]).toEqual(["feed", "league:NBA"]);
    expect([...toggleFilterSet(new Set(["source:one"]), "source:one")]).toEqual(["all"]);
    expect([...toggleFilterSet(active, "all")]).toEqual(["all"]);
  });
});

describe("feedFilters", () => {
  describe("filter families", () => {
    it("exposes all four decision levels as spectrum filters", () => {
      expect(LEVEL_FILTER_IDS).toEqual(["push", "high_feed", "feed", "low_feed"]);
    });

    it("keeps the expected topic chip ids in order", () => {
      expect(TOPIC_CHIPS.map((c) => c.id)).toEqual([
        "maccabi",
        "basketball",
        "NBA",
        "international",
      ]);
    });
  });

  describe("getVisibleItems", () => {
    it("drops hidden and decision-less items", () => {
      const items = [
        mk({ id: 1, score: { decision: "push" } }),
        mk({ id: 2, score: { decision: "hidden" } }),
        mk({ id: 3, score: {} }),
        mk({ id: 4, score: { decision: "low_feed" } }),
      ];
      expect(getVisibleItems(items).map((i) => i.id)).toEqual([1, 4]);
    });
  });

  describe("itemMatchesFilter", () => {
    it("matches every decision level by exact decision", () => {
      expect(itemMatchesFilter(mk({ score: { decision: "push" } }), "push")).toBe(true);
      expect(itemMatchesFilter(mk({ score: { decision: "feed" } }), "push")).toBe(false);
      expect(itemMatchesFilter(mk({ score: { decision: "high_feed" } }), "high_feed")).toBe(true);
      expect(itemMatchesFilter(mk({ score: { decision: "feed" } }), "feed")).toBe(true);
      expect(itemMatchesFilter(mk({ score: { decision: "low_feed" } }), "low_feed")).toBe(true);
      expect(itemMatchesFilter(mk({ score: { decision: "low_feed" } }), "feed")).toBe(false);
    });

    it("matches maccabi via entities (case-insensitive) or Hebrew tags", () => {
      expect(itemMatchesFilter(mk({ entities: ["Maccabi Tel Aviv"] }), "maccabi")).toBe(true);
      expect(itemMatchesFilter(mk({ tags: ["מכבי"] }), "maccabi")).toBe(true);
      expect(itemMatchesFilter(mk({ entities: ["Real Madrid"] }), "maccabi")).toBe(false);
    });

    it("matches basketball by sport and NBA by league", () => {
      expect(itemMatchesFilter(mk({ sport: "basketball" }), "basketball")).toBe(true);
      expect(itemMatchesFilter(mk({ sport: "football" }), "basketball")).toBe(false);
      expect(itemMatchesFilter(mk({ league: "NBA" }), "NBA")).toBe(true);
    });

    it("matches international sources for standalone and cluster items", () => {
      expect(itemMatchesFilter(mk({ source: "sportando" }), "international")).toBe(true);
      expect(itemMatchesFilter(mk({ source: "walla_sport" }), "international")).toBe(false);
      expect(
        itemMatchesFilter(mk({ type: "cluster", sources: ["walla_sport", "eurohoops"] }), "international")
      ).toBe(true);
      expect(
        itemMatchesFilter(mk({ type: "cluster", sources: ["walla_sport"] }), "international")
      ).toBe(false);
    });

    it("returns true for unknown filters (all)", () => {
      expect(itemMatchesFilter(mk(), "all")).toBe(true);
    });
  });

  describe("league filters (the league pills, #464)", () => {
    it("gives each item one league filter id, falling back to its sport, then to none", () => {
      expect(leagueFilterId(mk({ league: "EuroLeague", sport: "basketball" }))).toBe("league:EuroLeague");
      expect(leagueFilterId(mk({ league: null, sport: "football" }))).toBe("league:none:football");
      expect(leagueFilterId(mk({}))).toBe("league:none");
    });

    it("matches an item only by its own league id", () => {
      const euro = mk({ league: "EuroLeague", sport: "basketball" });
      expect(itemMatchesFilter(euro, "league:EuroLeague")).toBe(true);
      expect(itemMatchesFilter(euro, "league:NBA")).toBe(false);
      // A league-less basketball story is not swallowed by every basketball league.
      const loose = mk({ sport: "basketball" });
      expect(itemMatchesFilter(loose, "league:none:basketball")).toBe(true);
      expect(itemMatchesFilter(euro, "league:none:basketball")).toBe(false);
    });

    it("reads a cluster's league from its displayed article, like every other filter", () => {
      const cluster = mk({ type: "cluster", league: "NBA", sources: ["one", "walla_sport"] });
      expect(itemMatchesFilter(cluster, "league:NBA")).toBe(true);
      expect(itemMatchesFilter(cluster, "league:EuroLeague")).toBe(false);
    });

    it("ORs league ids with the same toggle semantics as the other families", () => {
      const items = [
        mk({ id: "e", league: "EuroLeague" }),
        mk({ id: "n", league: "NBA" }),
        mk({ id: "i", league: "Israeli Basketball League" }),
      ];
      let active = toggleFilterSet(new Set(["all"]), "league:NBA");
      active = toggleFilterSet(active, "league:EuroLeague");
      expect(filterFeedItems(items, active).map((i) => i.id)).toEqual(["e", "n"]);
      active = toggleFilterSet(toggleFilterSet(active, "league:NBA"), "league:EuroLeague");
      expect([...active]).toEqual(["all"]);
    });
  });

  describe("filterFeedItems", () => {
    const items = [
      mk({ id: "p", score: { decision: "push" }, sport: "basketball" }),
      mk({ id: "f", score: { decision: "feed" }, sport: "football" }),
      mk({ id: "n", score: { decision: "feed" }, league: "NBA" }),
    ];

    it("returns everything when 'all' is active", () => {
      expect(filterFeedItems(items, new Set(["all"])).map((i) => i.id)).toEqual(["p", "f", "n"]);
    });

    it("ORs levels with each other and ANDs them with topic filters", () => {
      expect(filterFeedItems(items, new Set(["push", "feed"])).map((i) => i.id)).toEqual(["p", "f", "n"]);
      expect(filterFeedItems(items, new Set(["push", "NBA"])).map((i) => i.id)).toEqual([]);
      expect(filterFeedItems(items, new Set(["feed", "NBA"])).map((i) => i.id)).toEqual(["n"]);
    });
  });

  describe("toggleFilterSet", () => {
    it("selecting 'all' resets to just all", () => {
      expect([...toggleFilterSet(new Set(["push", "NBA"]), "all")]).toEqual(["all"]);
    });

    it("selecting a chip clears 'all' and adds it", () => {
      expect([...toggleFilterSet(new Set(["all"]), "push")]).toEqual(["push"]);
    });

    it("re-selecting a chip removes it", () => {
      expect([...toggleFilterSet(new Set(["push", "NBA"]), "push")]).toEqual(["NBA"]);
    });

    it("removing the last chip falls back to 'all'", () => {
      expect([...toggleFilterSet(new Set(["push"]), "push")]).toEqual(["all"]);
    });
  });

  describe("importance levels as exact checkboxes (#510)", () => {
    const items = [
      mk({ id: "p", score: { decision: "push" }, league: "NBA", source: "one" }),
      mk({ id: "h1", score: { decision: "high_feed" }, league: "EuroLeague", source: "walla" }),
      mk({ id: "h2", score: { decision: "high_feed" }, league: "NBA", source: "walla" }),
      mk({ id: "f1", score: { decision: "feed" }, league: "EuroLeague", source: "one" }),
      mk({ id: "f2", score: { decision: "feed" }, league: "NBA", source: "walla" }),
      mk({ id: "l", score: { decision: "low_feed" }, league: "EuroLeague", source: "one" }),
    ];
    const ids = (list) => list.map((i) => i.id);
    const run = (active) => ids(filterFeedItems(items, new Set(active)));

    it("only regular selects exactly the feed items, in order", () => {
      expect(run(["feed"])).toEqual(["f1", "f2"]);
      expect(run(["low_feed"])).toEqual(["l"]);
    });

    it("several levels are OR; regular + important + push is 'regular and up'", () => {
      expect(run(["feed", "high_feed"])).toEqual(["h1", "h2", "f1", "f2"]);
      expect(run(["push", "high_feed", "feed"])).toEqual(["p", "h1", "h2", "f1", "f2"]);
    });

    it("ANDs importance with leagues and sources", () => {
      expect(run(["feed", "high_feed", "league:NBA"])).toEqual(["h2", "f2"]);
      expect(run(["feed", "high_feed", "league:NBA", "source:walla"])).toEqual(["h2", "f2"]);
      expect(run(["feed", "league:NBA", "source:one"])).toEqual([]);
    });

    it("never passes hidden or decision-less items", () => {
      expect(isVisibleItem(mk({ score: { decision: "hidden" } }))).toBe(false);
      expect(isVisibleItem(mk({ score: {} }))).toBe(false);
      expect(isVisibleItem(items[5])).toBe(true);
    });

    it("only narrows: the result is always a subset of what it was given", () => {
      const withHidden = [...items, mk({ id: "x", score: { decision: "hidden" }, league: "NBA" })];
      const visible = getVisibleItems(withHidden);
      for (const active of [["feed"], ["high_feed", "feed", "league:NBA"], ["all"]]) {
        const result = filterFeedItems(visible, new Set(active));
        expect(result.every((item) => visible.includes(item))).toBe(true);
        expect(ids(result)).not.toContain("x");
      }
    });

    it("toggles levels independently and keeps the other families", () => {
      let active = toggleFilterSet(new Set(["all"]), "league:NBA");
      active = toggleFilterSet(active, "feed");
      active = toggleFilterSet(active, "high_feed");
      expect([...active].sort()).toEqual(["feed", "high_feed", "league:NBA"]);
      active = toggleFilterSet(active, "feed");
      expect([...active].sort()).toEqual(["high_feed", "league:NBA"]);
      active = toggleFilterSet(active, "league:NBA");
      expect([...active]).toEqual(["high_feed"]);
    });

    it("clears one family with its '*' id and everything with 'all'", () => {
      const both = new Set(["high_feed", "feed", "league:NBA", "league:EuroLeague"]);
      expect([...toggleFilterSet(both, ALL_LEAGUES_ID)].sort()).toEqual(["feed", "high_feed"]);
      expect([...toggleFilterSet(both, ALL_LEVELS_ID)].sort()).toEqual(["league:EuroLeague", "league:NBA"]);
      expect([...toggleFilterSet(new Set(["league:NBA"]), ALL_LEAGUES_ID)]).toEqual(["all"]);
      expect([...toggleFilterSet(both, "all")]).toEqual(["all"]);
      // The '*' ids are commands, never stored.
      expect(toggleFilterSet(new Set(["all"]), ALL_LEAGUES_ID).has(ALL_LEAGUES_ID)).toBe(false);
    });

    it("reads the active levels and leagues back", () => {
      const active = new Set(["feed", "push", "league:NBA"]);
      expect(activeLevelIds(active)).toEqual(["feed", "push"]);
      expect(activeLevelIds(new Set(["all"]))).toEqual([]);
      expect(activeLeagueIds(active)).toEqual(["league:NBA"]);
      expect(hasActiveFilters(active)).toBe(true);
      expect(hasActiveFilters(new Set(["all"]))).toBe(false);
    });

    it("counts exact levels within the selected leagues, labelled from DECISION_CONFIG", () => {
      const options = importanceOptions(items, new Set(["league:EuroLeague"]));
      expect(options.map((o) => [o.id, o.level, o.count])).toEqual([
        [ALL_LEVELS_ID, null, 3],
        ["push", "push", 0],
        ["high_feed", "high_feed", 1],
        ["feed", "feed", 1],
        ["low_feed", "low_feed", 1],
      ]);
      expect(options.map((o) => o.label).slice(0, 1)).toEqual(["הכול"]);
      expect(options.some((o) => o.label.includes("ומעלה"))).toBe(false);
      expect(importanceOptions(items, new Set(["feed", "push"])).map((o) => o.selected)).toEqual([
        false, true, false, true, false,
      ]);
      expect(importanceOptions(items, new Set(["all"]))[0].selected).toBe(true);
    });

    it("counts a level ignoring the other selected levels", () => {
      const counts = importanceOptions(items, new Set(["feed", "league:NBA"])).map((o) => o.count);
      expect(counts).toEqual([3, 1, 1, 1, 0]);
    });

    it("never counts a hidden or decision-less item", () => {
      const withHidden = [...items, mk({ id: "x", score: { decision: "hidden" }, league: "NBA" }), mk({ id: "y", score: {} })];
      expect(visibleCount(withHidden)).toBe(6);
      expect(importanceOptions(withHidden, new Set(["all"]))[0].count).toBe(6);
      expect(facetedLeagueCounts(withHidden, new Set(["all"])).get("league:NBA")).toBe(3);
    });

    it("counts each league within the active floor (what pressing it would show)", () => {
      const counts = facetedLeagueCounts(items, new Set(["high_feed", "push", "league:EuroLeague"]));
      expect(counts.get("league:NBA")).toBe(2);
      expect(counts.get("league:EuroLeague")).toBe(1);
      expect(facetedLeagueCounts(items, new Set(["all"])).get("league:EuroLeague")).toBe(3);
    });
  });
});
