import React, { useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/context/AuthContext";
import { showCalibrateEmptyState } from "@/context/onboardingFlow";
import FeedFreshness from "@/components/feed/FeedFreshness";
import { feedBodyState } from "@/components/feed/feedLoadModel";
import SignalFeedView from "@/components/feed/signal/SignalFeedView";
import {
  SignalFeedEmpty,
  SignalFeedError,
  SignalFeedLoading,
} from "@/components/feed/signal/SignalFeedStates";
import { prepareFeedItems } from "@/components/feed/storyModel";
import { getVisibleItems, toggleFilterSet } from "@/components/feed/feedFilters";

export default function Feed() {
  const {
    feedItems,
    resultsGames,
    scoredArticles,
    activeProfileId,
    isBackendMode,
    isLoading,
    feedLoadFailed,
    refreshFeed,
  } = useApp();
  const auth = useAuth();
  const reduce = useReducedMotion();
  const [activeFilters, setActiveFilters] = useState(new Set(["all"]));

  const visibleItems = useMemo(() => getVisibleItems(feedItems), [feedItems]);
  // Backend clusters are authoritative; local/mock clusters need hydrating.
  // prepareFeedItems owns that split — see storyModel.
  const storyItems = useMemo(
    () => prepareFeedItems(visibleItems, { isBackendMode, localScoredArticles: scoredArticles }),
    [isBackendMode, scoredArticles, visibleItems]
  );

  const toggleFilter = (id) => {
    setActiveFilters((current) => toggleFilterSet(current, id));
  };
  const resetFilters = () => setActiveFilters(new Set(["all"]));

  const bodyState = feedBodyState({
    isBackendMode,
    isLoading,
    loadFailed: feedLoadFailed,
    itemCount: visibleItems.length,
  });

  if (bodyState === "loading") {
    return (
      <SignalFeedLoading />
    );
  }

  const freshness = <FeedFreshness enabled={isBackendMode} />;
  const emptyStateVariant = showCalibrateEmptyState(auth) ? "calibrate" : "default";

  return (
    <motion.div
      key={activeProfileId || "none"}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduce ? 0.12 : 0.34, ease: [0.22, 1, 0.36, 1] }}
    >
      {bodyState === "error" ? (
        <SignalFeedError onRetry={refreshFeed} status={freshness} />
      ) : bodyState === "empty" ? (
        <SignalFeedEmpty variant={emptyStateVariant} status={freshness} />
      ) : (
        <SignalFeedView
          items={storyItems}
          results={resultsGames}
          localScoredArticles={isBackendMode ? [] : scoredArticles}
          activeFilters={activeFilters}
          onToggleFilter={toggleFilter}
          onResetFilters={resetFilters}
          status={freshness}
        />
      )}
    </motion.div>
  );
}
