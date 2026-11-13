import { describe, expect, it } from "vitest";
import { filterFeedItems } from "@/components/feed/feedFilters";
import {
  IMPORTANT_ROW_SIZE,
  feedSummary,
  leaguePills,
  showMoreFocusIndex,
  splitFeedSections,
} from "./feedLayoutModel";

const story = (id, decision, over = {}) => ({ id, score: { decision }, ...over });
const ids = (list) => list.map((item) => item.id);

describe("splitFeedSections", () => {
  it("has no lead without a push: nothing is promoted to fill the space", () => {
    const items = [story("h1", "high_feed"), story("f1", "feed"), story("l1", "low_feed")];
    const sections = splitFeedSections(items);
    expect(sections.lead).toBeNull();
    expect(ids(sections.important)).toEqual(["h1"]);
    expect(ids(sections.stream)).toEqual(["f1"]);
    expect(ids(sections.brief)).toEqual(["l1"]);
  });

  it("leads with the first push; further pushes open the important row ahead of high_feed", () => {
    const items = [
      story("h1", "high_feed"),
      story("p1", "push"),
      story("p2", "push"),
      story("h2", "high_feed"),
    ];
    const sections = splitFeedSections(items);
    expect(sections.lead.id).toBe("p1");
    expect(ids(sections.important)).toEqual(["p2", "h1", "h2"]);
  });

  it("caps the important row at four; the rest continue at the top of the stream in rank order", () => {
    const items = [
      ...["h1", "h2", "h3", "h4", "h5", "h6"].map((id) => story(id, "high_feed")),
      story("f1", "feed"),
      story("f2", "feed"),
    ];
    const sections = splitFeedSections(items);
    expect(IMPORTANT_ROW_SIZE).toBe(4);
    expect(ids(sections.important)).toEqual(["h1", "h2", "h3", "h4"]);
    expect(ids(sections.stream)).toEqual(["h5", "h6", "f1", "f2"]);
  });

  it("places every visible story exactly once and keeps the ranked order inside each section", () => {
    const items = [
      story("f1", "feed"),
      story("l1", "low_feed"),
      story("h1", "high_feed"),
      story("f2", "feed"),
      story("p1", "push"),
      story("l2", "low_feed"),
    ];
    const { lead, important, stream, brief } = splitFeedSections(items);
    const placed = [lead, ...important, ...stream, ...brief].filter(Boolean);
    expect(ids(placed).sort()).toEqual(ids(items).sort());
    expect(ids(stream)).toEqual(["f1", "f2"]);
    expect(ids(brief)).toEqual(["l1", "l2"]);
  });

  it("never places a hidden or decision-less item, even if one slips through", () => {
    const items = [story("x", "hidden"), story("y", undefined), story("f1", "feed")];
    const { lead, important, stream, brief } = splitFeedSections(items);
    expect(ids([lead, ...important, ...stream, ...brief].filter(Boolean))).toEqual(["f1"]);
  });

  it("returns the same object identities it was given (backend items pass through untouched)", () => {
    const item = story("p1", "push");
    expect(splitFeedSections([item]).lead).toBe(item);
  });
});

describe("leaguePills", () => {
  const items = [
    story("a", "feed", { league: "EuroLeague", sport: "basketball" }),
    story("b", "feed", { league: "NBA", sport: "basketball" }),
    story("c", "feed", { league: "NBA", sport: "basketball" }),
    story("d", "feed", { league: "WNBA", sport: "basketball" }),
    story("e", "feed", { league: null, sport: "football" }),
  ];

  it("counts stories per league, highest first, ties in order of first appearance", () => {
    expect(leaguePills(items).map(({ id, count }) => [id, count])).toEqual([
      ["league:NBA", 2],
      ["league:EuroLeague", 1],
      ["league:WNBA", 1],
      ["league:none:football", 1],
    ]);
  });

  it("labels leagues in Hebrew where a name exists and keeps the original otherwise", () => {
    const labels = Object.fromEntries(leaguePills(items).map((pill) => [pill.id, pill.label]));
    expect(labels["league:EuroLeague"]).toBe("יורוליג");
    expect(labels["league:WNBA"]).toBe("WNBA");
    expect(labels["league:none:football"]).toBe("כדורגל");
  });

  it("each pill's count is exactly what selecting it shows", () => {
    for (const pill of leaguePills(items)) {
      expect(filterFeedItems(items, new Set([pill.id]))).toHaveLength(pill.count);
    }
  });

  it("is empty for an empty feed", () => {
    expect(leaguePills([])).toEqual([]);
  });
});

describe("feedSummary", () => {
  it("counts the visible stories and the important ones (push + high_feed)", () => {
    const items = [
      story("p", "push"),
      story("h", "high_feed"),
      story("f", "feed"),
      story("l", "low_feed"),
      story("x", "hidden"),
    ];
    expect(feedSummary(items)).toMatchObject({ stories: 4, important: 2 });
  });

  it("speaks Hebrew number agreement", () => {
    expect(feedSummary([story("f", "feed")]).storiesPhrase).toBe("סיפור עבר את הסינון שלך");
    expect(feedSummary([story("f", "feed"), story("g", "feed")]).storiesPhrase).toBe(
      "סיפורים עברו את הסינון שלך"
    );
    expect(feedSummary([story("h", "high_feed")]).importantPhrase).toBe("חשוב");
    expect(feedSummary([]).importantPhrase).toBe("חשובים");
  });
});

describe("showMoreFocusIndex", () => {
  it("moves focus to the first newly revealed row", () => {
    expect(showMoreFocusIndex(40, 80)).toBe(40);
    expect(showMoreFocusIndex(40, 47)).toBe(40);
  });

  it("has nowhere to go when nothing new was revealed", () => {
    expect(showMoreFocusIndex(40, 40)).toBeNull();
    expect(showMoreFocusIndex(40, 12)).toBeNull();
  });
});
