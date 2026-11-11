import React, { useState, useMemo, useCallback, useEffect } from "react";
import { AppContext } from "./appContextCore";
import { feedSources } from "@/data/feedSources";
import ErrorState from "@/components/shared/ErrorState";
import {
  getProfiles, getFeed, getDebugFeed, submitFeedback, neverShow,
  getMeFeed, getMeProfile, submitMeFeedback, meNeverShow,
  getMeResults, getResults,
} from "@/api/client";
import { recordArticleOpened } from "@/api/usage";
import { normalizeResultsResponse } from "@/components/results/resultsModel";
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
} from "@/api/normalizers";

const DATA_MODE = import.meta.env.VITE_DATA_MODE || "local";

// Backend feedback actions supported by the API
const BACKEND_VALID_ACTIONS = new Set([
  "more_like_this",
  "less_like_this",
  "not_interested",
  "never_show",
  "mute_source",
  "always_notify",
]);

const NO_LOCAL_FEED = { scoredArticles: [], feedItems: [], debugItems: [] };
const NO_RESULTS = { hasPreferences: false, games: [] };

function reloadPage() {
  window.location.reload();
}

// Local mode's mock data and engine live in their own chunk (#199), so a backend
// build's first load carries none of it. Nothing renders in local mode until it
// arrives: every screen there assumes the seed profiles exist.
function useLocalDemo() {
  const [state, setState] = useState({ demo: null, failed: false });
  useEffect(() => {
    if (DATA_MODE === "backend") return;
    let cancelled = false;
    import("@/context/localDemo").then(
      (demo) => { if (!cancelled) setState({ demo, failed: false }); },
      (err) => {
        console.error("local demo failed to load", err);
        if (!cancelled) setState({ demo: null, failed: true });
      },
    );
    return () => { cancelled = true; };
  }, []);
  return state;
}

export function AppProvider({ children }) {
  const auth = useAuth();
  const { demo, failed } = useLocalDemo();
  if (failed) {
    return (
      <ErrorState
        variant="page"
        title="לא הצלחנו לטעון את מצב ההדגמה"
        onRetry={reloadPage}
        retryLabel="טען מחדש"
      />
    );
  }
  if (DATA_MODE !== "backend" && !demo) return null;
  // Personal data and outstanding requests belong to one session identity.
  // Remount on login/logout/account switch so previous-user state cannot leak.
  return (
    <AppStateProvider key={`${auth.authEnforced}:${auth.user?.id ?? "anonymous"}`} localDemo={demo}>
      {children}
    </AppStateProvider>
  );
}

function AppStateProvider({ children, localDemo }) {
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
  // An admin consumer session may browse any user's feed from the product
  // page (not just the ops console) via the same view-as target used there.
  // Non-admin consumer sessions never get this — canFetchQaSurface is false
  // for them, so this is precisely the admin case.
  const adminViewAs = consumerSession && qaSurfaceAllowed;
  const feedbackUsesSession = consumerSession && !adminViewAs;

  // The session user's own profile (product surface under enforcement).
  const [meProfile, setMeProfile] = useState(null);

  // ── Local state (used in both modes) ────────────────────────────────────────
  const [activeProfileId, setActiveProfileId] = useState("guy");
  const feedbackUserId = feedbackUsesSession ? consumerUserId : activeProfileId;
  // Demo profiles are a local-mode concept; backend mode has none to start from.
  const [profiles, setProfiles] = useState(() => localDemo?.userProfiles ?? {});
  const [sandboxProfile, setSandboxProfile] = useState(null);
  const [sources, setSources] = useState(feedSources);
  const [feedback, setFeedback] = useState([]);

  // ── Backend-only state ───────────────────────────────────────────────────────
  const [backendProfiles, setBackendProfiles] = useState([]);
  const [backendFeedItems, setBackendFeedItems] = useState([]);
  const [backendDebugItems, setBackendDebugItems] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState(null);
  // The product feed request itself failed (D5) — distinct from other API errors.
  const [feedLoadFailed, setFeedLoadFailed] = useState(false);
  // Used to trigger manual refresh without changing activeProfileId
  const [feedRefreshTick, setFeedRefreshTick] = useState(0);

  // ── Results (issue #178) ──────────────────────────────────────────────────
  const [backendResults, setBackendResults] = useState({ hasPreferences: false, games: [] });
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState(null);
  const [resultsRefreshTick, setResultsRefreshTick] = useState(0);

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

  // Default the view-as target to the admin's own profile on login, so the
  // product feed starts out showing their own feed until they switch.
  useEffect(() => {
    if (adminViewAs && consumerUserId) setActiveProfileId(consumerUserId);
  }, [adminViewAs, consumerUserId]);

  // ── Load feeds whenever identity or refresh tick changes ────────────────────
  // Product feed: the view-as target ({user_id}) for admins (local/bypass
  // behave the same way), the session identity (/api/me/feed) for non-admin
  // consumer sessions. QA debug feed: view-as identity, fetched only when
  // this client may touch the admin surface (bypass/local, or admin).
  useEffect(() => {
    if (!isBackendMode || fetchesBlocked) return;
    let cancelled = false;
    setIsLoading(true);
    setApiError(null);
    const productFeedPromise = consumerSession && !adminViewAs
      ? getMeFeed()
      : getFeed(activeProfileId);
    const debugFeedPromise = qaSurfaceAllowed
      ? getDebugFeed(activeProfileId)
      : Promise.resolve([]);
    Promise.all([productFeedPromise, debugFeedPromise])
      .then(([feedRaw, debugRaw]) => {
        if (cancelled) return;
        setFeedLoadFailed(false);
        setBackendFeedItems(feedRaw.map(normalizeScoredArticleFromApi));
        setBackendDebugItems(debugRaw.map(normalizeScoredArticleFromApi));
      })
      .catch(err => {
        if (cancelled) return;
        setFeedLoadFailed(true);
        setApiError(err.message);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  }, [isBackendMode, fetchesBlocked, consumerSession, consumerUserId,
      qaSurfaceAllowed, adminViewAs, activeProfileId, feedRefreshTick]);

  // ── Load personalized results (backend mode) ────────────────────────────────
  // Consumer sessions use the session identity (/api/me/results); admin view-as
  // and bypass/local-QA use the {user_id} route. The server enforces relevance
  // and isolation — the client never filters.
  useEffect(() => {
    if (!isBackendMode || fetchesBlocked) return;
    let cancelled = false;
    setResultsLoading(true);
    setResultsError(null);
    const promise = consumerSession && !adminViewAs
      ? getMeResults()
      : getResults(activeProfileId);
    promise
      .then((raw) => {
        if (cancelled) return;
        setBackendResults(normalizeResultsResponse(raw));
      })
      .catch((err) => {
        if (cancelled) return;
        setResultsError(err.message);
      })
      .finally(() => {
        if (!cancelled) setResultsLoading(false);
      });
    return () => { cancelled = true; };
  }, [isBackendMode, fetchesBlocked, consumerSession, consumerUserId,
      adminViewAs, activeProfileId, resultsRefreshTick]);

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

  const localFeed = useMemo(() => {
    if (!localDemo) return NO_LOCAL_FEED;
    return localDemo.computeLocalFeed(allProfiles[activeProfileId], disabledSourceIds);
  }, [localDemo, activeProfileId, allProfiles, disabledSourceIds]);

  // ── Local-mode results (offline demo) — same normalize→relevance path ───────
  const localResults = useMemo(() => {
    if (!localDemo) return NO_RESULTS;
    return localDemo.computeLocalResults(allProfiles[activeProfileId]);
  }, [localDemo, allProfiles, activeProfileId]);

  // ── Resolved values (switch between modes) ───────────────────────────────────
  const feedItems = isBackendMode ? backendFeedItems : localFeed.feedItems;
  const debugItems = isBackendMode ? backendDebugItems : localFeed.debugItems;
  const resultsData = isBackendMode ? backendResults : localResults;

  const backendProfilesMap = useMemo(() => {
    const map = {};
    backendProfiles.forEach(p => { map[p.userId] = p; });
    return map;
  }, [backendProfiles]);

  const backendProfileList = useMemo(() => {
    return backendProfiles.map(p => ({ id: p.userId, label: p.displayName }));
  }, [backendProfiles]);

  const activeProfile = consumerSession && !adminViewAs
    ? meProfile
    : isBackendMode
      ? (backendProfilesMap[activeProfileId] ?? meProfile ?? null)
      : (allProfiles[activeProfileId] ?? null);

  const resolvedProfileList = isBackendMode ? backendProfileList : profileList;

  // ── Manual refresh helpers ───────────────────────────────────────────────────
  const refreshFeed = useCallback(() => {
    if (isBackendMode) setFeedRefreshTick(n => n + 1);
  }, [isBackendMode]);

  const refreshResults = useCallback(() => {
    if (isBackendMode) setResultsRefreshTick(n => n + 1);
  }, [isBackendMode]);

  // ── Feedback ────────────────────────────────────────────────────────────────
  // Returns a promise that settles with the server's answer (#197): it
  // rejects when the save failed, so the caller can say so instead of
  // claiming success. Local mode has no server and resolves at once.
  const addFeedback = useCallback((articleId, action) => {
    // Optimistic local record, reconciled below if the save fails.
    const entry = {
      id: `feedback_${Date.now()}`,
      userId: feedbackUserId,
      articleId,
      action,
      createdAt: new Date().toISOString(),
    };
    setFeedback(prev => [...prev, entry]);

    // Feedback follows the displayed feed identity: regular users use /me;
    // admin view-as and bypass use the explicit, server-guarded target.
    if (isBackendMode && BACKEND_VALID_ACTIONS.has(action)) {
      const post = feedbackUsesSession
        ? submitMeFeedback(articleId, action)
        : submitFeedback({
            user_id: activeProfileId,
            article_id: articleId,
            action,
          });
      return post.then(() => {
        // Dismissing actions hide the article immediately (issue #34) —
        // refresh so the feed reflects it.
        if (action === "less_like_this" || action === "not_interested" || action === "never_show") {
          refreshFeed();
        }
        return entry;
      }, (err) => {
        // Never stored: drop the optimistic record and let the caller show it.
        setFeedback(prev => prev.filter(f => f !== entry));
        throw err;
      });
    }
    return Promise.resolve(entry);
  }, [activeProfileId, feedbackUserId, isBackendMode, feedbackUsesSession, refreshFeed]);

  // Explicit scoped suppression (issue #34): creates a never_show override
  // for the most specific scope on the article, then refreshes the feed.
  // A failure propagates to the caller (#197); the feed refreshes either way,
  // since the override may have been stored before the feedback event failed.
  const neverShowArticle = useCallback(async (articleId) => {
    if (!isBackendMode) return;
    try {
      if (feedbackUsesSession) {
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
    } finally {
      refreshFeed();
    }
  }, [activeProfileId, isBackendMode, feedbackUsesSession, refreshFeed]);

  // Reader opened an article's source (#250): only the reader's own session counts —
  // never an admin view-as — and it never enters the local feedback list.
  const noteArticleOpened = useCallback((articleId) => {
    recordArticleOpened(articleId, {
      enabled: isBackendMode && feedbackUsesSession,
      send: submitMeFeedback,
    });
  }, [isBackendMode, feedbackUsesSession]);

  const getFeedbackForArticle = useCallback((articleId) => {
    return feedback.filter(f => f.userId === feedbackUserId && f.articleId === articleId);
  }, [feedback, feedbackUserId]);

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
    feedLoadFailed,
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

    // Results (issue #178)
    resultsGames: resultsData.games,
    resultsHasPreferences: resultsData.hasPreferences,
    resultsLoading,
    resultsError,
    refreshResults,
    scoredArticles: localFeed.scoredArticles,

    // Sources
    sources,
    disabledSourceIds,
    toggleSource,

    // Feedback
    feedback,
    addFeedback,
    neverShowArticle,
    getFeedbackForArticle,
    noteArticleOpened,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

// The hooks live with the context object, so provider-free bundles can use them (#458).
export { useApp, useArticleOpened, useEngineTraceVisible } from "./appContextCore";
