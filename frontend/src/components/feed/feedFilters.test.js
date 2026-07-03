import { describe, it, expect } from "vitest";
import {
  FILTER_CHIPS,
  getVisibleItems,
  itemMatchesFilter,
  filterFeedItems,
  toggleFilterSet,
} from "./feedFilters";

const mk = (over = {}) => ({ score: { decision: "feed" }, ...over });

describe("feedFilters", () => {
  describe("FILTER_CHIPS", () => {
    it("keeps the expected chip ids in order", () => {
      expect(FILTER_CHIPS.map((c) => c.id)).toEqual([
        "all",
        "push",
        "high_feed",
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
    it("matches push/high_feed by decision", () => {
      expect(itemMatchesFilter(mk({ score: { decision: "push" } }), "push")).toBe(true);
      expect(itemMatchesFilter(mk({ score: { decision: "feed" } }), "push")).toBe(false);
      expect(itemMatchesFilter(mk({ score: { decision: "high_feed" } }), "high_feed")).toBe(true);
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
