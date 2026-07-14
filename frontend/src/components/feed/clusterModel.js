/**
 * Story-cluster presentation model (#104) — ALL LOGIC, NO JSX.
 *
 * The repo's frontend convention (cf. interestsModel.js, feedFilters.js): components render,
 * models decide. Vitest runs in a `node` environment with no DOM, so every rule that could be
 * wrong lives here and is unit-tested directly.
 *
 * The invariant these functions exist to protect: a cluster card shows VISIBLE members only.
 * Suppressed members never reach the consumer payload (docs/CLUSTERING.md §9) — but the UI
 * must not rely on that alone, so the consumer-facing selectors here never look at them.
 */

export function isCluster(item) {
  return item?.type === "cluster";
}

/** VISIBLE source count. Never counts a suppressed member. */
export function clusterSourceCount(item) {
  if (!isCluster(item)) return 0;
  return item.sourceCount ?? (item.members?.length ?? 0);
}

/**
 * The alternate coverage listed under "עוד מקורות".
 * The main card already shows the displayed member, so it is excluded here.
 */
export function clusterAlternates(item) {
  if (!isCluster(item)) return [];
  return (item.members ?? []).filter(m => m.articleId !== item.primaryArticleId);
}

/** A single-source "cluster" has nothing to disclose. */
export function shouldShowSources(item) {
  return isCluster(item) && clusterSourceCount(item) >= 2;
}

/** The card's update timestamp — the newest VISIBLE member, never a hidden one. */
export function clusterUpdatedAt(item) {
  return isCluster(item) ? (item.lastUpdatedAt ?? item.publishedAt ?? null) : null;
}

/**
 * The decision that RANKS the card: MAX over the user's visible members.
 * Deliberately distinct from the displayed article's own decision, which clustering
 * never changes.
 */
export function clusterCardDecision(item) {
  return item?.score?.decision ?? null;
}

export function clusterArticleDecision(item) {
  return item?.articleScoreDecision ?? null;
}

const DISPLAY_REASON_HE = {
  representative_visible: "הנציג הגלובלי גלוי — מוצג",
  representative_hidden_fallback: "הנציג הגלובלי מוסתר — נבחר החבר הגלוי הטוב ביותר",
};

/** Everything Debug needs to explain (and disprove) a cluster. */
export function clusterDebugRoles(item) {
  if (!isCluster(item)) return null;
  return {
    clusterId: item.clusterId,
    ruleVersion: item.ruleVersion ?? null,
    eventState: item.eventState ?? null,
    representativeArticleId: item.representativeArticleId ?? null,
    displayedArticleId: item.primaryArticleId,
    priorityArticleId: item.priorityArticleId,
    displayedReason: item.displayedReason,
    displayedReasonLabel:
      DISPLAY_REASON_HE[item.displayedReason] ?? item.displayedReason,
    cardDecision: clusterCardDecision(item),
    articleDecision: clusterArticleDecision(item),
    visibleMembers: item.members ?? [],
    // Debug ONLY. Empty in the consumer payload by construction.
    suppressedMembers: item.suppressedMembers ?? [],
  };
}
