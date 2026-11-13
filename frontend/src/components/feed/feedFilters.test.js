import { describe, it, expect } from "vitest";
import {
  LEVEL_FILTER_IDS,
  TOPIC_CHIPS,
  getVisibleItems,
  itemMatchesFilter,
  filterFeedItems,
  leagueFilterId,
  toggleFilterSet,
} from "./feedFilters";

const mk = (over = {}) => ({ score: { decision: "feed" }, ...over });

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

    it("ORs multiple active filters", () => {
      const res = filterFeedItems(items, new Set(["push", "NBA"]));
      expect(res.map((i) => i.id).sort()).toEqual(["n", "p"]);
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
});
