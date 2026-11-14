import { describe, expect, it } from "vitest";
import { filterFeedItems } from "@/components/feed/feedFilters";
import {
  IMPORTANT_ROW_SIZE,
  LATEST_SIZE,
  feedSummary,
  isFreshStory,
  latestStories,
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

describe("latestStories (the side column's \"אחרונים\", #465)", () => {
  const NOW = Date.parse("2026-11-13T18:00:00Z");
  const at = (minutesAgo) => new Date(NOW - minutesAgo * 60_000).toISOString();
  const timed = (id, decision, minutesAgo, over = {}) =>
    story(id, decision, { publishedAt: minutesAgo == null ? null : at(minutesAgo), ...over });

  it("lists the visible non-low stories newest first, whatever their rank", () => {
    const items = [
      timed("p", "push", 300),
      timed("h", "high_feed", 30),
      timed("f", "feed", 5),
      timed("l", "low_feed", 1),
      timed("x", "hidden", 2),
      timed("n", undefined, 3),
    ];
    expect(ids(latestStories(items))).toEqual(["f", "h", "p"]);
  });

  it("shows at most LATEST_SIZE stories, and all of them when there are fewer", () => {
    const many = Array.from({ length: 40 }, (_, index) => timed(`f${index}`, "feed", index));
    expect(LATEST_SIZE).toBe(8);
    expect(ids(latestStories(many))).toEqual(ids(many.slice(0, 8)));
    const few = [timed("a", "feed", 90), timed("b", "high_feed", 10), timed("c", "feed", 50)];
    expect(ids(latestStories(few))).toEqual(["b", "c", "a"]);
  });

  it("never reorders or removes anything from the ranked stream", () => {
    const items = [timed("f1", "feed", 120), timed("f2", "feed", 1), timed("f3", "feed", 60)];
    const before = ids(items);
    const streamBefore = ids(splitFeedSections(items).stream);
    latestStories(items);
    expect(ids(items)).toEqual(before);
    expect(ids(splitFeedSections(items).stream)).toEqual(streamBefore);
  });

  it("orders a cluster by its backend update time, not its first report", () => {
    const cluster = timed("c", "feed", 600, { type: "cluster", lastUpdatedAt: at(2) });
    const single = timed("s", "feed", 10);
    expect(ids(latestStories([single, cluster]))).toEqual(["c", "s"]);
  });

  it("leaves out a story with no readable time (it stays in the stream) and keeps rank order on ties", () => {
    const items = [timed("a", "feed", 20), timed("u", "feed", null), timed("b", "feed", 20)];
    expect(ids(latestStories(items))).toEqual(["a", "b"]);
  });

  it("follows the active league filter, like the stream", () => {
    const items = [
      timed("nba", "feed", 5, { league: "NBA" }),
      timed("el", "feed", 1, { league: "EuroLeague" }),
    ];
    const filtered = filterFeedItems(items, new Set(["league:NBA"]));
    expect(ids(latestStories(filtered))).toEqual(["nba"]);
  });
});

describe("isFreshStory", () => {
  const NOW = Date.parse("2026-11-13T18:00:00Z");

  it("marks a story under an hour old", () => {
    expect(isFreshStory(new Date(NOW - 59 * 60_000).toISOString(), NOW)).toBe(true);
    expect(isFreshStory(new Date(NOW - 61 * 60_000).toISOString(), NOW)).toBe(false);
  });

  it("does not mark a missing or unreadable time", () => {
    expect(isFreshStory(null, NOW)).toBe(false);
    expect(isFreshStory("not a date", NOW)).toBe(false);
  });
});
