import { describe, expect, it } from "vitest";
import {
  orbitFeedbackArticleId,
  orbitHasMultiSourceField,
  orbitQueueItems,
  orbitUniqueSourceCount,
  hydrateLocalClusters,
  prepareFeedItems,
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
    const prepared = hydrateLocalClusters([localCluster], [
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

// The backend/local split must be structural, not a coincidence of the two
// calculations agreeing. Backend cluster truth is test-locked server-side
// (docs/CLUSTERING.md §9) and mapped straight through by normalizers.js.
describe("prepareFeedItems — cluster value authority", () => {
  // Shaped exactly as normalizers.js emits a backend cluster.
  const backendCluster = Object.freeze({
    id: "displayed-article",
    clusterId: "story-9",
    type: "cluster",
    clusterTitle: "הכותרת מהשרת",
    primaryArticleId: "b2",
    representativeArticleId: "b2",
    priorityArticleId: "b1",
    displayedReason: "representative_visible",
    sourceCount: 2,
    lastUpdatedAt: "2026-07-27T10:00:00Z",
    firstSeenAt: "2026-07-27T08:00:00Z",
    members: Object.freeze([
      Object.freeze({
        articleId: "b2", source: "one", sourceDisplayName: "ONE",
        title: "דיווח שני", url: "https://example.test/2",
        publishedAt: "2026-07-27T10:00:00Z", decision: "push",
      }),
      Object.freeze({
        articleId: "b1", source: "sport5", sourceDisplayName: "ספורט 5",
        title: "דיווח ראשון", url: "https://example.test/1",
        publishedAt: "2026-07-27T08:00:00Z", decision: "feed",
      }),
    ]),
    articleIds: ["b2", "b1"],
    sources: ["one", "sport5"],
    sourceDisplayNames: ["ONE", "ספורט 5"],
    score: { decision: "push" },
  });

  const backendArticle = Object.freeze({
    id: "solo", type: "article", title: "כתבה בודדת",
    source: "walla_sport", publishedAt: "2026-07-27T11:00:00Z",
    score: { decision: "feed" },
  });

  describe("backend mode", () => {
    const items = [backendCluster, backendArticle];

    it("passes the list through without rebuilding it", () => {
      const result = prepareFeedItems(items, { isBackendMode: true });
      expect(result).toBe(items);
    });

    it("keeps every item object identical", () => {
      const [cardResult, articleResult] = prepareFeedItems(items, { isBackendMode: true });
      expect(cardResult).toBe(backendCluster);
      expect(articleResult).toBe(backendArticle);
    });

    // Each value the frontend used to recompute, named explicitly so a
    // reintroduced rewrite fails here rather than drifting silently.
    it.each([
      ["members", "members"],
      ["sourceCount", "sourceCount"],
      ["primaryArticleId", "primaryArticleId"],
      ["clusterTitle", "clusterTitle"],
      ["lastUpdatedAt", "lastUpdatedAt"],
    ])("leaves backend-authoritative %s untouched", (_name, key) => {
      const [card] = prepareFeedItems(items, { isBackendMode: true });
      expect(card[key]).toBe(backendCluster[key]);
    });

    it("ignores localScoredArticles entirely", () => {
      const decoy = [
        { id: "b2", source: "impostor", title: "לא אמור להופיע",
          publishedAt: "2026-07-27T23:00:00Z", score: { decision: "feed" } },
      ];
      const [card] = prepareFeedItems(items, {
        isBackendMode: true, localScoredArticles: decoy,
      });
      expect(card).toBe(backendCluster);
      expect(card.sourceCount).toBe(2);
      expect(card.lastUpdatedAt).toBe("2026-07-27T10:00:00Z");
    });

    // Debug renders the raw payload; the consumer feed must agree with it.
    it("agrees with Debug on source count and canonical article identity", () => {
      const debugView = backendCluster; // Debug consumes debugItems untouched
      const [consumerView] = prepareFeedItems(items, { isBackendMode: true });
      expect(consumerView.sourceCount).toBe(debugView.sourceCount);
      expect(consumerView.primaryArticleId).toBe(debugView.primaryArticleId);
      expect(consumerView.representativeArticleId).toBe(debugView.representativeArticleId);
      expect(consumerView.clusterTitle).toBe(debugView.clusterTitle);
      expect(consumerView.lastUpdatedAt).toBe(debugView.lastUpdatedAt);
    });

    it("reads reports straight from the backend members", () => {
      const [card] = prepareFeedItems(items, { isBackendMode: true });
      const reports = orbitStoryReports(card, []);
      expect(reports.map((report) => report.articleId)).toEqual(["b2", "b1"]);
      expect(orbitUniqueSourceCount(reports)).toBe(card.sourceCount);
    });
  });

  describe("local mode", () => {
    const localCluster = {
      id: "local-displayed",
      clusterId: "local-9",
      type: "cluster",
      clusterTitle: "כותרת מקומית",
      primaryArticleId: "l1",
      articleIds: ["l1", "l2"],
      score: { decision: "feed" },
    };
    const scored = [
      { id: "l1", source: "sport5", sourceDisplayName: "ספורט 5", title: "ראשון",
        publishedAt: "2026-07-27T08:00:00Z", score: { decision: "feed" } },
      { id: "l2", source: "one", sourceDisplayName: "ONE", title: "שני",
        publishedAt: "2026-07-27T09:30:00Z", score: { decision: "high_feed" } },
    ];

    it("hydrates members from the scored catalogue", () => {
      const [card] = prepareFeedItems([localCluster], {
        isBackendMode: false, localScoredArticles: scored,
      });
      expect(card).not.toBe(localCluster);
      expect(card.members.map((member) => member.articleId)).toEqual(["l1", "l2"]);
      expect(card.sourceCount).toBe(2);
      expect(card.lastUpdatedAt).toBe("2026-07-27T09:30:00Z");
    });

    it("still drops locally hidden members", () => {
      const [card] = prepareFeedItems([localCluster], {
        isBackendMode: false,
        localScoredArticles: [scored[0], { ...scored[1], score: { decision: "hidden" } }],
      });
      expect(card.sourceCount).toBe(1);
      expect(card.members.map((member) => member.articleId)).toEqual(["l1"]);
    });

    it("leaves plain local articles alone", () => {
      const article = { id: "x", type: "article", score: { decision: "feed" } };
      const [result] = prepareFeedItems([article], {
        isBackendMode: false, localScoredArticles: scored,
      });
      expect(result).toBe(article);
    });

    it("survives a missing catalogue without throwing", () => {
      expect(() => prepareFeedItems([localCluster], { isBackendMode: false })).not.toThrow();
    });
  });

  it("defaults to hydrating when no mode is supplied", () => {
    expect(() => prepareFeedItems([])).not.toThrow();
    expect(prepareFeedItems([])).toEqual([]);
  });
});
