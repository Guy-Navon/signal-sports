import { describe, expect, it } from "vitest";
import {
  orbitFeedbackArticleId,
  orbitHasMultiSourceField,
  orbitQueueItems,
  orbitUniqueSourceCount,
  prepareOrbitItems,
  resolveOrbitFocus,
  orbitStoryId,
  orbitStoryReports,
  orbitStorySourceLine,
  reportsChronologically,
  reportsWithPrimaryFirst,
  detectNewSource,
  selectOrbitFocus,
  sourceInitial,
} from "./orbitStoryModel";

const cluster = {
  id: "displayed-article",
  clusterId: "story-1",
  type: "cluster",
  primaryArticleId: "a2",
  sourceDisplayNames: ["ONE", "ספורט 5"],
  members: [
    {
      articleId: "a1",
      source: "sport5",
      sourceDisplayName: "ספורט 5",
      title: "דיווח ראשון",
      publishedAt: "2026-07-27T08:00:00Z",
      decision: "feed",
    },
    {
      articleId: "a2",
      source: "one",
      sourceDisplayName: "ONE",
      title: "דיווח שני",
      publishedAt: "2026-07-27T09:00:00Z",
      decision: "push",
    },
  ],
  // This must never be consulted by the consumer adapter.
  suppressedMembers: [
    {
      articleId: "secret",
      sourceDisplayName: "מקור מוסתר",
      decision: "hidden",
    },
  ],
};

describe("Orbit story adapter", () => {
  it("uses stable story identity while keeping feedback article-owned", () => {
    expect(orbitStoryId(cluster)).toBe("story-1");
    expect(orbitFeedbackArticleId(cluster, orbitStoryReports(cluster))).toBe("a2");
  });

  it("reads only visible cluster members", () => {
    const reports = orbitStoryReports(cluster);
    expect(reports.map((report) => report.articleId)).toEqual(["a1", "a2"]);
    expect(reports.some((report) => report.articleId === "secret")).toBe(false);
  });

  it("hydrates legacy local clusters from scored visible articles", () => {
    const localCluster = { ...cluster, members: undefined, articleIds: ["a1", "a2", "a3"] };
    const reports = orbitStoryReports(localCluster, [
      { id: "a1", source: "one", title: "א", score: { decision: "feed" } },
      { id: "a2", source: "sport5", title: "ב", score: { decision: "push" } },
      { id: "a3", source: "muted", title: "ג", score: { decision: "hidden" } },
    ]);
    expect(reports.map((report) => report.articleId)).toEqual(["a1", "a2"]);
  });

  it("can order reports for the compact field or a chronological expansion", () => {
    const reports = orbitStoryReports(cluster);
    expect(reportsWithPrimaryFirst(cluster, reports)[0].articleId).toBe("a2");
    expect(reportsChronologically(reports).map((report) => report.articleId)).toEqual([
      "a1",
      "a2",
    ]);
  });

  it("derives the displayed source from the primary report", () => {
    expect(orbitStorySourceLine(cluster, orbitStoryReports(cluster))).toBe("ONE");
  });

  it("preserves upstream order when choosing a focus and queue", () => {
    const items = [
      { id: "first", type: "article" },
      { id: "second", type: "article" },
      { id: "third", type: "article" },
    ];
    expect(selectOrbitFocus(items).id).toBe("first");
    expect(orbitQueueItems(items, items[1]).map((item) => item.id)).toEqual([
      "first",
      "third",
    ]);
  });

  it("follows a new leader until the user explicitly pins a story", () => {
    const original = [
      { id: "first", type: "article" },
      { id: "second", type: "article" },
    ];
    expect(resolveOrbitFocus(original, null)).toEqual({
      item: original[0],
      isPinned: false,
    });
    const reordered = [{ id: "urgent", type: "article" }, ...original];
    expect(resolveOrbitFocus(reordered, null).item.id).toBe("urgent");
    expect(resolveOrbitFocus(reordered, "second")).toEqual({
      item: original[1],
      isPinned: true,
    });
  });

  it("counts unique visible sources and gates multi-source disclosure", () => {
    const duplicate = {
      articleId: "a3",
      source: "one",
      sourceDisplayName: "ONE",
      decision: "feed",
    };
    const reports = [...orbitStoryReports(cluster), duplicate];
    expect(orbitUniqueSourceCount(reports)).toBe(2);
    expect(orbitHasMultiSourceField({ ...cluster, sourceCount: 2 }, reports)).toBe(true);
    expect(
      orbitHasMultiSourceField(
        { ...cluster, sourceCount: 1 },
        reports.filter((report) => report.source === "one")
      )
    ).toBe(false);
  });

  it("detects a genuinely new source, not another report from an existing source", () => {
    const before = orbitStoryReports(cluster);
    expect(
      detectNewSource(before, [
        ...before,
        { articleId: "a4", source: "one", sourceDisplayName: "ONE" },
      ])
    ).toBeNull();
    expect(
      detectNewSource(before, [
        ...before,
        { articleId: "a5", source: "ynet", sourceDisplayName: "ynet" },
      ])?.articleId
    ).toBe("a5");
  });

  it("sanitizes local source metadata, freshness, title, and feedback identity", () => {
    const localCluster = {
      ...cluster,
      members: undefined,
      articleIds: ["hidden-primary", "visible"],
      primaryArticleId: "hidden-primary",
      clusterTitle: "כותרת מוסתרת",
      sources: ["foreign-hidden", "sport5"],
      lastUpdatedAt: "2026-07-27T12:00:00Z",
    };
    const prepared = prepareOrbitItems([localCluster], [
      {
        id: "hidden-primary",
        source: "foreign-hidden",
        title: "כותרת מוסתרת",
        publishedAt: "2026-07-27T12:00:00Z",
        score: { decision: "hidden" },
      },
      {
        id: "visible",
        source: "sport5",
        sourceDisplayName: "ספורט 5",
        title: "כותרת גלויה",
        publishedAt: "2026-07-27T09:00:00Z",
        score: { decision: "feed" },
      },
    ])[0];
    expect(prepared.primaryArticleId).toBe("visible");
    expect(prepared.clusterTitle).toBe("כותרת גלויה");
    expect(prepared.sources).toEqual(["sport5"]);
    expect(prepared.lastUpdatedAt).toBe("2026-07-27T09:00:00Z");
    expect(orbitFeedbackArticleId(prepared, prepared.members)).toBe("visible");
  });

  it("creates source initials for Hebrew and Latin identities", () => {
    expect(sourceInitial("ספורט 5")).toBe("ס");
    expect(sourceInitial("one")).toBe("O");
  });
});
