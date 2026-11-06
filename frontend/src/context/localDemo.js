// Local (mock) mode's data and computations, in their own chunk (#199): a build
// talking to the real backend never loads this module on a normal session. Only
// local mode imports it at startup; backend mode only when an admin opens the
// Debug page's profile comparison tab.
import { userProfiles } from "@/data/userProfiles";
import { mockArticles, mockClusters } from "@/data/mockArticles";
import { mockResults } from "@/data/mockResults";
import { scoreAllArticles, scoreCluster, scoreArticle, DECISION_RANK } from "@/engine/relevanceEngine";
import { normalizeResultFromApi } from "@/components/results/resultsModel";
import { deriveFollows, filterRelevant, hasAnyFollows } from "@/components/results/resultsRelevance";

export { userProfiles };

const clusteredArticleIds = new Set(mockClusters.flatMap(c => c.articleIds));

export function computeLocalFeed(profile, disabledSourceIds) {
  const options = { disabledSourceIds };
  const scoredArticles = scoreAllArticles(mockArticles, profile, options);
  const scoredClusters = mockClusters.map(cluster =>
    scoreCluster(cluster, mockArticles, profile, options)
  );
  const standalone = scoredArticles.filter(a => !clusteredArticleIds.has(a.id));

  const feedItems = [
    ...scoredClusters.map(c => ({ ...c, type: "cluster" })),
    ...standalone.map(a => ({ ...a, type: "article" })),
  ].sort((a, b) => {
    const rankDiff = DECISION_RANK[b.score?.decision || "hidden"] - DECISION_RANK[a.score?.decision || "hidden"];
    if (rankDiff !== 0) return rankDiff;
    const aDate = new Date(a.publishedAt || a.firstSeenAt);
    const bDate = new Date(b.publishedAt || b.firstSeenAt);
    return bDate.getTime() - aDate.getTime();
  });

  const debugItems = [
    ...scoredClusters.map(c => ({ ...c, type: "cluster", displayTitle: c.clusterTitle })),
    ...standalone.map(a => ({ ...a, type: "article", displayTitle: a.title })),
  ].sort((a, b) => DECISION_RANK[b.score?.decision || "hidden"] - DECISION_RANK[a.score?.decision || "hidden"]);

  return { scoredArticles, feedItems, debugItems };
}

export function computeLocalResults(profile) {
  if (!profile) return { hasPreferences: false, games: [] };
  const follows = deriveFollows(profile);
  return {
    hasPreferences: hasAnyFollows(follows),
    games: filterRelevant(mockResults.map(normalizeResultFromApi), follows),
  };
}

// The demo cross-profile comparison: mock articles scored by the local engine,
// in either data mode (Debug's compare tab).
export function computeProfileComparison(profilesById, disabledSourceIds) {
  const profiles = Object.values(profilesById);
  const options = { disabledSourceIds };
  const clusterItems = mockClusters.map(cluster => {
    const profileScores = {};
    profiles.forEach(p => {
      profileScores[p.userId] = scoreCluster(cluster, mockArticles, p, options).score;
    });
    return { ...cluster, type: "cluster", profileScores };
  });
  const articleItems = mockArticles
    .filter(a => !clusteredArticleIds.has(a.id))
    .map(article => {
      const profileScores = {};
      profiles.forEach(p => {
        profileScores[p.userId] = scoreArticle(article, p, options);
      });
      return { ...article, type: "article", profileScores };
    });
  return [...clusterItems, ...articleItems].sort((a, b) => {
    const aMax = Math.max(...Object.values(a.profileScores).map(s => DECISION_RANK[s.decision] || 0));
    const bMax = Math.max(...Object.values(b.profileScores).map(s => DECISION_RANK[s.decision] || 0));
    return bMax - aMax;
  });
}
