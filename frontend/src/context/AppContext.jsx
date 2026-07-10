import React, { createContext, useContext, useState, useMemo, useCallback, useEffect, useRef } from "react";
import { userProfiles } from "@/data/userProfiles";
import { mockArticles, mockClusters } from "@/data/mockArticles";
import { feedSources } from "@/data/feedSources";
import { scoreAllArticles, scoreCluster, scoreArticle, DECISION_RANK } from "@/engine/relevanceEngine";
import {
  getProfiles, getFeed, getDebugFeed, submitFeedback, getCalibrationHeadlines, neverShow,
  getMeFeed, getMeProfile, submitMeFeedback, meNeverShow,
} from "@/api/client";
import { useAuth } from "@/context/AuthContext";
import {
  isConsumerSession as computeConsumerSession,
  canFetchQaSurface,
  backendFetchesBlocked,
} from "@/context/dataRouting";
// Sandbox preview profile id (was in the deleted draftToProfile.js — the
// calibration flow is backend-owned since issue #33).
export const SANDBOX_PROFILE_ID = "calibrated_sandbox";

import {
  normalizeProfileFromApi,
  normalizeScoredArticleFromApi,
  normalizeCalibrationHeadlineFromApi,
} from "@/api/normalizers";

const DATA_MODE = import.meta.env.VITE_DATA_MODE || "local";

const AppContext = createContext(null);

// Backend feedback actions supported by the API
const BACKEND_VALID_ACTIONS = new Set([
  "more_like_this",
  "less_like_this",
  "not_interested",
  "never_show",
  "mute_source",
  "always_notify",
]);

export function AppProvider({ children }) {
  const isBackendMode = DATA_MODE === "backend";

  // Consumer/QA split (User Platform PR 5, #53). Under real enforcement with
  // a signed-in user the PRODUCT surface uses /api/me/* (session identity)
  // while activeProfileId becomes the ops-console QA view-as identity only.
  // Local mode and bypass keep the pre-auth single-identity behavior exactly.
  const auth = useAuth();
  const authView = {
    isBackendMode,
    authStatus: auth.status,
    authEnforced: auth.authEnforced,
    user: auth.user,
  };
  const consumerSession = computeConsumerSession(authView);
  const qaSurfaceAllowed = canFetchQaSurface(authView);
  const fetchesBlocked = backendFetchesBlocked(authView);
  const consumerUserId = consumerSession ? auth.user.id : null;

  // The session user's own profile (product surface under enforcement).
  const [meProfile, setMeProfile] = useState(null);

  // ── Local state (used in both modes) ────────────────────────────────────────
  const [activeProfileId, setActiveProfileId] = useState("guy");
  const [profiles, setProfiles] = useState(userProfiles);
  const [sandboxProfile, setSandboxProfile] = useState(null);
  const [sources, setSources] = useState(feedSources);
  const [feedback, setFeedback] = useState([]);

  // ── Backend-only state ───────────────────────────────────────────────────────
  const [backendProfiles, setBackendProfiles] = useState([]);
  const [backendFeedItems, setBackendFeedItems] = useState([]);
  const [backendDebugItems, setBackendDebugItems] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState(null);
  // Used to trigger manual refresh without changing activeProfileId
  const [feedRefreshTick, setFeedRefreshTick] = useState(0);

  // ── Load backend profiles once (QA surface — admin/bypass only) ─────────────
  useEffect(() => {
    if (!isBackendMode || fetchesBlocked || !qaSurfaceAllowed) return;
    getProfiles()
      .then(raw => setBackendProfiles(raw.map(normalizeProfileFromApi)))
      .catch(err => setApiError(err.message));
  }, [isBackendMode, fetchesBlocked, qaSurfaceAllowed]);

  // ── Load the session user's own profile (consumer surface) ──────────────────
  useEffect(() => {
    if (!consumerSession) {
      setMeProfile(null);
      return;
    }
    getMeProfile()
      .then(raw => setMeProfile(normalizeProfileFromApi(raw)))
      .catch(err => setApiError(err.message));
  }, [consumerSession, consumerUserId]);

  // ── Load feeds whenever identity or refresh tick changes ────────────────────
  // Product feed: session identity (/api/me/feed) under a consumer session,
  // legacy {user_id} otherwise. QA debug feed: view-as identity, fetched only
  // when this client may touch the admin surface (bypass/local, or admin).
  useEffect(() => {
    if (!isBackendMode || fetchesBlocked) return;
    let cancelled = false;
    setIsLoading(true);
    setApiError(null);
    const productFeedPromise = consumerSession ? getMeFeed() : getFeed(activeProfileId);
    const debugFeedPromise = qaSurfaceAllowed
      ? getDebugFeed(activeProfileId)
      : Promise.resolve([]);
    Promise.all([productFeedPromise, debugFeedPromise])
      .then(([feedRaw, debugRaw]) => {
        if (cancelled) return;
        setBackendFeedItems(feedRaw.map(normalizeScoredArticleFromApi));
        setBackendDebugItems(debugRaw.map(normalizeScoredArticleFromApi));
      })
      .catch(err => {
        if (cancelled) return;
        setApiError(err.message);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  }, [isBackendMode, fetchesBlocked, consumerSession, consumerUserId,
      qaSurfaceAllowed, activeProfileId, feedRefreshTick]);

  // ── Local computed state (only used in local mode) ───────────────────────────
  const allProfiles = useMemo(() => ({
    ...profiles,
    ...(sandboxProfile ? { [SANDBOX_PROFILE_ID]: sandboxProfile } : {})
  }), [profiles, sandboxProfile]);

  const profileList = useMemo(() => {
    const list = Object.values(profiles).map(p => ({
      id: p.userId,
      label: p.displayName
    }));
    if (sandboxProfile) {
      list.push({ id: sandboxProfile.userId, label: sandboxProfile.displayName });
    }
    return list;
  }, [profiles, sandboxProfile]);

  const disabledSourceIds = useMemo(() => {
    return new Set(sources.filter(s => !s.enabled).map(s => s.id));
  }, [sources]);

  const scoredArticles = useMemo(() => {
    if (isBackendMode) return [];
    return scoreAllArticles(mockArticles, allProfiles[activeProfileId], { disabledSourceIds });
  }, [isBackendMode, activeProfileId, allProfiles, disabledSourceIds]);

  const scoredClusters = useMemo(() => {
    if (isBackendMode) return [];
    return mockClusters.map(cluster =>
      scoreCluster(cluster, mockArticles, allProfiles[activeProfileId], { disabledSourceIds })
    );
  }, [isBackendMode, activeProfileId, allProfiles, disabledSourceIds]);

  const clusteredArticleIds = useMemo(() => {
    return new Set(mockClusters.flatMap(c => c.articleIds));
  }, []);

  const localFeedItems = useMemo(() => {
    const clusterItems = scoredClusters.map(c => ({ ...c, type: "cluster" }));
    const standaloneItems = scoredArticles
      .filter(a => !clusteredArticleIds.has(a.id))
      .map(a => ({ ...a, type: "article" }));
    return [...clusterItems, ...standaloneItems].sort((a, b) => {
      const rankDiff = DECISION_RANK[b.score?.decision || "hidden"] - DECISION_RANK[a.score?.decision || "hidden"];
      if (rankDiff !== 0) return rankDiff;
      const aDate = new Date(a.publishedAt || a.firstSeenAt);
      const bDate = new Date(b.publishedAt || b.firstSeenAt);
      return bDate - aDate;
    });
  }, [scoredClusters, scoredArticles, clusteredArticleIds]);

  const localDebugItems = useMemo(() => {
    const clusterItems = scoredClusters.map(c => ({
      ...c, type: "cluster", displayTitle: c.clusterTitle
    }));
    const standaloneItems = scoredArticles
      .filter(a => !clusteredArticleIds.has(a.id))
      .map(a => ({ ...a, type: "article", displayTitle: a.title }));
    return [...clusterItems, ...standaloneItems].sort((a, b) => {
      return DECISION_RANK[b.score?.decision || "hidden"] - DECISION_RANK[a.score?.decision || "hidden"];
    });
  }, [scoredClusters, scoredArticles, clusteredArticleIds]);

  // Comparison always uses local engine (cross-profile comparison is local-only)
  const comparisonItems = useMemo(() => {
    const profilesForComparison = Object.values(allProfiles);
    const options = { disabledSourceIds };
    const standaloneArticles = mockArticles.filter(a => !clusteredArticleIds.has(a.id));
    const clusterItems = mockClusters.map(cluster => {
      const profileScores = {};
      profilesForComparison.forEach(p => {
        profileScores[p.userId] = scoreCluster(cluster, mockArticles, p, options).score;
      });
      return { ...cluster, type: "cluster", profileScores };
    });
    const articleItems = standaloneArticles.map(article => {
      const profileScores = {};
      profilesForComparison.forEach(p => {
        profileScores[p.userId] = scoreArticle(article, p, options);
      });
      return { ...article, type: "article", profileScores };
    });
    return [...clusterItems, ...articleItems].sort((a, b) => {
      const aMax = Math.max(...Object.values(a.profileScores).map(s => DECISION_RANK[s.decision] || 0));
      const bMax = Math.max(...Object.values(b.profileScores).map(s => DECISION_RANK[s.decision] || 0));
      return bMax - aMax;
    });
  }, [allProfiles, clusteredArticleIds, disabledSourceIds]);

  // ── Resolved values (switch between modes) ───────────────────────────────────
  const feedItems = isBackendMode ? backendFeedItems : localFeedItems;
  const debugItems = isBackendMode ? backendDebugItems : localDebugItems;

  const backendProfilesMap = useMemo(() => {
    const map = {};
    backendProfiles.forEach(p => { map[p.userId] = p; });
    return map;
  }, [backendProfiles]);

  const backendProfileList = useMemo(() => {
    return backendProfiles.map(p => ({ id: p.userId, label: p.displayName }));
  }, [backendProfiles]);

  const activeProfile = consumerSession
    ? meProfile
    : isBackendMode
      ? (backendProfilesMap[activeProfileId] ?? null)
      : (allProfiles[activeProfileId] ?? null);

  const resolvedProfileList = isBackendMode ? backendProfileList : profileList;

  // ── Manual refresh helpers ───────────────────────────────────────────────────
  const refreshFeed = useCallback(() => {
    if (isBackendMode) setFeedRefreshTick(n => n + 1);
  }, [isBackendMode]);

  // ── Feedback ────────────────────────────────────────────────────────────────
  const addFeedback = useCallback((articleId, action) => {
    // Track locally always
    const entry = {
      id: `feedback_${Date.now()}`,
      userId: activeProfileId,
      articleId,
      action,
      createdAt: new Date().toISOString(),
    };
    setFeedback(prev => [...prev, entry]);

    // In backend mode, POST to API for supported actions. Consumer sessions
    // go through /api/me/feedback (server-derived identity, #53); the legacy
    // body-identity form remains for bypass/QA use only.
    if (isBackendMode && BACKEND_VALID_ACTIONS.has(action)) {
      const post = consumerSession
        ? submitMeFeedback(articleId, action)
        : submitFeedback({
            user_id: activeProfileId,
            article_id: articleId,
            action,
          });
      post.then(() => {
        // Dismissing actions hide the article immediately (issue #34) —
        // refresh so the feed reflects it.
        if (action === "less_like_this" || action === "not_interested" || action === "never_show") {
          refreshFeed();
        }
      }).catch(() => {
        // Feedback failure is non-fatal; local state already recorded the event
      });
    }
  }, [activeProfileId, isBackendMode, consumerSession, refreshFeed]);

  // Explicit scoped suppression (issue #34): creates a never_show override
  // for the most specific scope on the article, then refreshes the feed.
  const neverShowArticle = useCallback(async (articleId) => {
    if (!isBackendMode) return;
    try {
      if (consumerSession) {
        await meNeverShow(articleId);
        await submitMeFeedback(articleId, "never_show");
      } else {
        await neverShow(activeProfileId, articleId);
        await submitFeedback({
          user_id: activeProfileId,
          article_id: articleId,
          action: "never_show",
        });
      }
    } catch {
      // non-fatal
    }
    refreshFeed();
  }, [activeProfileId, isBackendMode, consumerSession, refreshFeed]);

  const getFeedbackForArticle = useCallback((articleId) => {
    return feedback.filter(f => f.userId === activeProfileId && f.articleId === articleId);
  }, [feedback, activeProfileId]);

  // ── Source toggle ────────────────────────────────────────────────────────────
  const toggleSource = useCallback((sourceId) => {
    setSources(prev => prev.map(s =>
      s.id === sourceId ? { ...s, enabled: !s.enabled } : s
    ));
  }, []);

  // ── Profile management ───────────────────────────────────────────────────────
  const updateProfile = useCallback((profileId, updatedProfile) => {
    setProfiles(prev => ({ ...prev, [profileId]: updatedProfile }));
  }, []);

  const applySandboxProfile = useCallback((profile) => {
    setSandboxProfile(profile);
    setActiveProfileId(SANDBOX_PROFILE_ID);
  }, []);

  const resetSandboxProfile = useCallback(() => {
    setSandboxProfile(null);
    setActiveProfileId(current => current === SANDBOX_PROFILE_ID ? "guy" : current);
  }, []);

  const refreshProfiles = useCallback(() => {
    if (!isBackendMode) return;
    if (consumerSession) {
      getMeProfile()
        .then(raw => setMeProfile(normalizeProfileFromApi(raw)))
        .catch(err => setApiError(err.message));
    }
    if (qaSurfaceAllowed) {
      getProfiles()
        .then(raw => setBackendProfiles(raw.map(normalizeProfileFromApi)))
        .catch(err => setApiError(err.message));
    }
  }, [isBackendMode, consumerSession, qaSurfaceAllowed]);

  const value = {
    // Mode
    dataMode: DATA_MODE,
    isBackendMode,
    // Consumer/QA split (#53): product surface uses the session identity;
    // activeProfileId is the ops QA view-as identity under enforcement.
    consumerSession,
    qaSurfaceAllowed,
    isLoading,
    apiError,
    refreshFeed,
    refreshProfiles,

    // Profile
    activeProfileId,
    setActiveProfileId,
    activeProfile,
    profiles,
    allProfiles,
    profileList: resolvedProfileList,
    sandboxProfile,
    applySandboxProfile,
    resetSandboxProfile,
    updateProfile,

    // Feed
    feedItems,
    debugItems,
    comparisonItems,
    scoredArticles,
    scoredClusters,
    clusteredArticleIds,

    // Sources
    sources,
    toggleSource,

    // Feedback
    feedback,
    addFeedback,
    neverShowArticle,
    getFeedbackForArticle,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
