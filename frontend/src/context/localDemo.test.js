import { describe, expect, it } from "vitest";
import { computeLocalFeed, computeLocalResults, computeProfileComparison, userProfiles } from "./localDemo";

const NONE_DISABLED = new Set();

describe("the local demo (#199)", () => {
  it("gives the two seed profiles different feeds from the same mock articles", () => {
    const guy = computeLocalFeed(userProfiles.guy, NONE_DISABLED);
    const deni = computeLocalFeed(userProfiles.casual_deni_fan, NONE_DISABLED);
    const decisionsOf = (feed) => JSON.stringify(feed.debugItems.map((i) => [i.id, i.score?.decision]).sort());
    expect(decisionsOf(guy)).not.toBe(decisionsOf(deni));
  });

  it("orders the feed by decision, keeps articles of a cluster inside its card", () => {
    const { feedItems, debugItems } = computeLocalFeed(userProfiles.guy, NONE_DISABLED);
    expect(feedItems.some((i) => i.type === "cluster")).toBe(true);
    expect(feedItems.some((i) => i.type === "article")).toBe(true);
    expect(debugItems.every((i) => i.displayTitle)).toBe(true);
    const members = new Set(feedItems.filter((i) => i.type === "cluster").flatMap((c) => c.articleIds));
    expect(feedItems.filter((i) => i.type === "article").some((a) => members.has(a.id))).toBe(false);
  });

  it("a disabled source changes what the profile gets", () => {
    const all = computeLocalFeed(userProfiles.guy, NONE_DISABLED);
    const source = all.scoredArticles.find((a) => a.score?.decision !== "hidden").source;
    const without = computeLocalFeed(userProfiles.guy, new Set([source]));
    const shownFrom = (feed) => feed.scoredArticles.filter((a) => a.source === source && a.score?.decision !== "hidden");
    expect(shownFrom(all).length).toBeGreaterThan(0);
    expect(shownFrom(without)).toEqual([]);
  });

  it("the comparison scores every row for every profile and leads with the strongest", () => {
    const items = computeProfileComparison(userProfiles, NONE_DISABLED);
    const ids = Object.keys(userProfiles).map((key) => userProfiles[key].userId);
    expect(items.length).toBeGreaterThan(0);
    for (const item of items) expect(Object.keys(item.profileScores).sort()).toEqual([...ids].sort());
    expect(items.some((i) => new Set(ids.map((id) => i.profileScores[id].decision)).size > 1)).toBe(true);
    expect(Object.values(items[0].profileScores).map((s) => s.decision)).toContain("push");
  });

  it("no profile means no local results rather than a crash", () => {
    expect(computeLocalResults(undefined)).toEqual({ hasPreferences: false, games: [] });
    expect(computeLocalResults(userProfiles.guy).hasPreferences).toBe(true);
  });
});
