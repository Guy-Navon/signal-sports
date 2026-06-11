import React, { createContext, useContext, useState, useMemo, useCallback } from "react";
import { userProfiles } from "@/data/userProfiles";
import { mockArticles, mockClusters } from "@/data/mockArticles";
import { feedSources } from "@/data/feedSources";
import { scoreAllArticles, scoreCluster, scoreArticle, DECISION_RANK } from "@/engine/relevanceEngine";

const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [activeProfileId, setActiveProfileId] = useState("guy");
  const [profiles, setProfiles] = useState(userProfiles);
  const [sources, setSources] = useState(feedSources);
  const [feedback, setFeedback] = useState([]); // { id, userId, articleId, action, createdAt }

  const activeProfile = profiles[activeProfileId];

  // IDs of sources the user has disabled on the Sources page.
  // Disabled-source articles are scored as hidden (with reason "disabled_source")
  // so they appear in the debug view but not in the normal feed.
  const disabledSourceIds = useMemo(() => {
    return new Set(sources.filter(s => !s.enabled).map(s => s.id));
  }, [sources]);

  // Score all standalone articles (not in a cluster)
  const scoredArticles = useMemo(() => {
    return scoreAllArticles(mockArticles, activeProfile, { disabledSourceIds });
  }, [activeProfileId, profiles, disabledSourceIds]);

  // Score all clusters
  const scoredClusters = useMemo(() => {
    return mockClusters.map(cluster =>
      scoreCluster(cluster, mockArticles, activeProfile, { disabledSourceIds })
    );
  }, [activeProfileId, profiles, disabledSourceIds]);

  // Build feed items: clusters + standalone articles (those not in any cluster)
  const clusteredArticleIds = useMemo(() => {
    return new Set(mockClusters.flatMap(c => c.articleIds));
  }, []);

  // Feed items = scored clusters + standalone scored articles
  const feedItems = useMemo(() => {
    const clusterItems = scoredClusters.map(c => ({ ...c, type: "cluster" }));
    const standaloneItems = scoredArticles
      .filter(a => !clusteredArticleIds.has(a.id))
      .map(a => ({ ...a, type: "article" }));

    // Combine and sort by decision rank descending, then by date
    return [...clusterItems, ...standaloneItems].sort((a, b) => {
      const rankDiff = DECISION_RANK[b.score?.decision || "hidden"] - DECISION_RANK[a.score?.decision || "hidden"];
      if (rankDiff !== 0) return rankDiff;
      const aDate = new Date(a.publishedAt || a.firstSeenAt);
      const bDate = new Date(b.publishedAt || b.firstSeenAt);
      return bDate - aDate;
    });
  }, [scoredClusters, scoredArticles, clusteredArticleIds]);

  // Comparison data: score every standalone article against ALL profiles side by side
  const comparisonItems = useMemo(() => {
    const allProfiles = Object.values(profiles);
    const options = { disabledSourceIds };
    const standaloneArticles = mockArticles.filter(a => !clusteredArticleIds.has(a.id));
    const clusterItems = mockClusters.map(cluster => {
      const profileScores = {};
      allProfiles.forEach(p => {
        profileScores[p.userId] = scoreCluster(cluster, mockArticles, p, options).score;
      });
      return { ...cluster, type: "cluster", profileScores };
    });
    const articleItems = standaloneArticles.map(article => {
      const profileScores = {};
      allProfiles.forEach(p => {
        profileScores[p.userId] = scoreArticle(article, p, options);
      });
      return { ...article, type: "article", profileScores };
    });
    return [...clusterItems, ...articleItems].sort((a, b) => {
      // Sort by highest score across any profile
      const aMax = Math.max(...Object.values(a.profileScores).map(s => DECISION_RANK[s.decision] || 0));
      const bMax = Math.max(...Object.values(b.profileScores).map(s => DECISION_RANK[s.decision] || 0));
      return bMax - aMax;
    });
  }, [profiles, clusteredArticleIds, disabledSourceIds]);

  // All articles for debug panel (including hidden)
  const debugItems = useMemo(() => {
    const clusterItems = scoredClusters.map(c => ({
      ...c,
      type: "cluster",
      displayTitle: c.clusterTitle
    }));
    const standaloneItems = scoredArticles
      .filter(a => !clusteredArticleIds.has(a.id))
      .map(a => ({ ...a, type: "article", displayTitle: a.title }));

    return [...clusterItems, ...standaloneItems].sort((a, b) => {
      return DECISION_RANK[b.score?.decision || "hidden"] - DECISION_RANK[a.score?.decision || "hidden"];
    });
  }, [scoredClusters, scoredArticles, clusteredArticleIds]);

  // Feedback handler
  const addFeedback = useCallback((articleId, action) => {
    const entry = {
      id: `feedback_${Date.now()}`,
      userId: activeProfileId,
      articleId,
      action,
      createdAt: new Date().toISOString()
    };
    setFeedback(prev => [...prev, entry]);
  }, [activeProfileId]);

  const getFeedbackForArticle = useCallback((articleId) => {
    return feedback.filter(f => f.userId === activeProfileId && f.articleId === articleId);
  }, [feedback, activeProfileId]);

  // Source toggle
  const toggleSource = useCallback((sourceId) => {
    setSources(prev => prev.map(s =>
      s.id === sourceId ? { ...s, enabled: !s.enabled } : s
    ));
  }, []);

  // Update profile preferences
  const updateProfile = useCallback((profileId, updatedProfile) => {
    setProfiles(prev => ({ ...prev, [profileId]: updatedProfile }));
  }, []);

  const value = {
    activeProfileId,
    setActiveProfileId,
    activeProfile,
    profiles,
    updateProfile,
    sources,
    toggleSource,
    feedback,
    addFeedback,
    getFeedbackForArticle,
    feedItems,
    debugItems,
    comparisonItems,
    scoredArticles,
    scoredClusters,
    clusteredArticleIds
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}