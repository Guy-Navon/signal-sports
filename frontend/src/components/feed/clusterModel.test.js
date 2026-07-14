import { describe, it, expect } from "vitest";
import { normalizeScoredArticleFromApi } from "@/api/normalizers";
import {
  clusterAlternates,
  clusterArticleDecision,
  clusterCardDecision,
  clusterDebugRoles,
  clusterSourceCount,
  clusterUpdatedAt,
  isCluster,
  shouldShowSources,
} from "./clusterModel";

/**
 * Story-cluster presentation (#104).
 *
 * The invariant under test: a cluster card shows VISIBLE members only, and the CARD decision
 * (max over visible members) is distinct from the DISPLAYED ARTICLE's own decision — which
 * clustering never changes.
 */

const apiCluster = {
  decision: "feed",                       // the DISPLAYED ARTICLE's own decision
  article: {
    id: "a1", source: "walla_sport", source_display_name: "וואלה ספורט",
    url: "https://x/a1", title: "גרג לי חתם בהפועל חולון", language: "he",
    published_at: "2026-07-07T09:00:00Z", sport: "basketball", entities: [],
    event_type: "signing", importance: "high", tags: [], cluster_id: "cluster_abc",
  },
  cluster: {
    cluster_id: "cluster_abc",
    decision: "push",                     // the CARD decision (max over visible members)
    representative_article_id: "a2",      // hidden for this user → fallback fired
    displayed_article_id: "a1",
    priority_article_id: "a3",
    displayed_reason: "representative_hidden_fallback",
    source_count: 2,
    sort_at: "2026-07-07T11:00:00Z",
    members: [
      { article_id: "a1", source: "walla_sport", source_display_name: "וואלה ספורט",
        title: "כותרת א", url: "https://x/a1",
        published_at: "2026-07-07T09:00:00Z", decision: "feed" },
      { article_id: "a3", source: "sport5_sport", source_display_name: "ערוץ הספורט",
        title: "כותרת ג", url: "https://x/a3",
        published_at: "2026-07-07T11:00:00Z", decision: "push" },
    ],
    suppressed_members: [],               // consumer payload: ALWAYS empty
    rule_version: 1,
    event_state: "signing",
  },
};

// normalizeScoredArticleFromApi returns a union (article | cluster). TS narrows it, so the
// cluster-only props need an explicit cast in tests. The model accessors below are typed.
/** @type {any} */
const item = normalizeScoredArticleFromApi(apiCluster);

describe("cluster normalization", () => {
  it("maps the backend cluster payload onto the existing cluster item contract", () => {
    expect(item.type).toBe("cluster");
    expect(item.clusterId).toBe("cluster_abc");
    expect(item.clusterTitle).toBe("גרג לי חתם בהפועל חולון");
  });

  it("uses the CARD decision for ranking, not the displayed article's own", () => {
    expect(clusterCardDecision(item)).toBe("push");     // card
    expect(clusterArticleDecision(item)).toBe("feed");  // article, unchanged by clustering
  });

  it("keeps the three roles separate", () => {
    expect(item.representativeArticleId).toBe("a2");
    expect(item.primaryArticleId).toBe("a1");
    expect(item.priorityArticleId).toBe("a3");
    expect(item.displayedReason).toBe("representative_hidden_fallback");
  });

  it("takes the update timestamp from the newest VISIBLE member", () => {
    expect(clusterUpdatedAt(item)).toBe("2026-07-07T11:00:00Z");
  });

  it("carries no suppressed members in the consumer payload", () => {
    expect(item.suppressedMembers).toEqual([]);
  });

  it("leaves an unclustered article an ordinary item", () => {
    /** @type {any} */
    const plain = normalizeScoredArticleFromApi({ ...apiCluster, cluster: undefined });
    expect(plain.type).toBe("article");
    expect(plain.score.decision).toBe("feed");
    expect(isCluster(plain)).toBe(false);
  });
});

describe("consumer card: עוד מקורות", () => {
  it("reports the VISIBLE source count", () => {
    expect(clusterSourceCount(item)).toBe(2);
  });

  it("lists only the ALTERNATES — the main card already shows the displayed member", () => {
    const alts = clusterAlternates(item);
    expect(alts.map(m => m.articleId)).toEqual(["a3"]);
  });

  it("shows the disclosure only when there is more than one source", () => {
    expect(shouldShowSources(item)).toBe(true);
    const solo = { ...item, sourceCount: 1, members: item.members.slice(0, 1) };
    expect(shouldShowSources(solo)).toBe(false);
  });

  it("never surfaces a hidden member", () => {
    // The consumer payload has no suppressed members, and the selectors never read them.
    const alts = clusterAlternates(item);
    expect(alts.every(m => m.decision !== "hidden")).toBe(true);
  });

  it("returns nothing for a non-cluster item", () => {
    /** @type {any} */
    const plain = normalizeScoredArticleFromApi({ ...apiCluster, cluster: undefined });
    expect(shouldShowSources(plain)).toBe(false);
    expect(clusterAlternates(plain)).toEqual([]);
    expect(clusterSourceCount(plain)).toBe(0);
  });
});

describe("debug evidence", () => {
  // Debug is the ONLY surface that may show suppressed members.
  /** @type {any} */
  const debugItem = normalizeScoredArticleFromApi({
    ...apiCluster,
    cluster: {
      ...apiCluster.cluster,
      suppressed_members: [
        { article_id: "a2", source: "ynet_sport", source_display_name: "ynet ספורט",
          title: "כותרת מוסתרת", url: "https://x/a2",
          published_at: "2026-07-07T10:00:00Z", decision: "hidden" },
      ],
    },
  });

  it("returns null for a non-cluster item", () => {
    /** @type {any} */
    const plain = normalizeScoredArticleFromApi({ ...apiCluster, cluster: undefined });
    expect(clusterDebugRoles(plain)).toBeNull();
  });

  it("exposes cluster id, rule version and event state", () => {
    const r = clusterDebugRoles(debugItem);
    expect(r.clusterId).toBe("cluster_abc");
    expect(r.ruleVersion).toBe(1);
    expect(r.eventState).toBe("signing");
  });

  it("exposes all three member roles", () => {
    const r = clusterDebugRoles(debugItem);
    expect(r.representativeArticleId).toBe("a2");
    expect(r.displayedArticleId).toBe("a1");
    expect(r.priorityArticleId).toBe("a3");
  });

  it("explains WHY that member is displayed", () => {
    const r = clusterDebugRoles(debugItem);
    expect(r.displayedReasonLabel).toContain("הנציג הגלובלי מוסתר");
  });

  it("proves clustering caused no article-level drift", () => {
    const r = clusterDebugRoles(debugItem);
    expect(r.cardDecision).toBe("push");      // max over visible members
    expect(r.articleDecision).toBe("feed");   // the article itself — unchanged
  });

  it("is the only surface that shows suppressed members", () => {
    const r = clusterDebugRoles(debugItem);
    expect(r.suppressedMembers.map(m => m.articleId)).toEqual(["a2"]);
    expect(r.suppressedMembers[0].decision).toBe("hidden");
    // …and the consumer item for the same cluster has none.
    expect(clusterDebugRoles(item).suppressedMembers).toEqual([]);
  });
});
