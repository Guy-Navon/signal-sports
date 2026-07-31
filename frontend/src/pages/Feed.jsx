import React, { useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/context/AuthContext";
import { showCalibrateEmptyState } from "@/context/onboardingFlow";
import EditionEmptyState from "@/components/feed/EditionEmptyState";
import OrbitFeedView from "@/components/feed/orbit/OrbitFeedView";
import { prepareFeedItems } from "@/components/feed/orbit/orbitStoryModel";
import {
  filterFeedItems,
  getVisibleItems,
  toggleFilterSet,
} from "@/components/feed/feedFilters";
import "@/components/feed/orbit/orbit.css";

function OrbitLoadingState() {
  return (
    <div className="orbit-loading" aria-busy="true" aria-label="טוען את המסלול האישי">
      <div className="orbit-loading__heading">
        <i />
        <i />
      </div>
      <div className="orbit-loading__filters" />
      <div className="orbit-loading__layout">
        <div className="orbit-loading__field">
          <span className="orbit-loading__ring" />
          <div className="orbit-loading__core">
            <i />
            <i />
            <i />
            <i />
          </div>
        </div>
        <div className="orbit-loading__queue">
          {[0, 1, 2, 3].map((index) => (
            <div key={index}>
              <i />
              <i />
              <i />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Feed() {
  const {
    feedItems,
    debugItems,
    scoredArticles,
    activeProfileId,
    activeProfile,
    isBackendMode,
    isLoading,
  } = useApp();
  const auth = useAuth();
  const reduce = useReducedMotion();
  const [activeFilters, setActiveFilters] = useState(new Set(["all"]));

  const visibleItems = useMemo(() => getVisibleItems(feedItems), [feedItems]);
  // Backend clusters are authoritative; local/mock clusters need hydrating.
  // prepareFeedItems owns that split — see orbitStoryModel.
  const orbitItems = useMemo(
    () => prepareFeedItems(visibleItems, { isBackendMode, localScoredArticles: scoredArticles }),
    [isBackendMode, scoredArticles, visibleItems]
  );
  const filteredItems = useMemo(
    () => filterFeedItems(orbitItems, activeFilters),
    [activeFilters, orbitItems]
  );
  const decisionCounts = useMemo(() => {
    const counts = { push: 0, high_feed: 0, feed: 0, low_feed: 0 };
    for (const item of orbitItems) {
      const decision = item.score?.decision;
      if (decision in counts) counts[decision] += 1;
    }
    return counts;
  }, [orbitItems]);

  const toggleFilter = (id) => {
    setActiveFilters((current) => toggleFilterSet(current, id));
  };
  const resetFilters = () => setActiveFilters(new Set(["all"]));

  if (isBackendMode && isLoading && visibleItems.length === 0) {
    return (
      <div className="orbit-feed-view">
        <OrbitLoadingState />
      </div>
    );
  }

  const emptyStateVariant = showCalibrateEmptyState(auth) ? "calibrate" : "default";

  return (
    <motion.div
      key={activeProfileId || "none"}
      className="orbit-feed-controller"
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduce ? 0.12 : 0.34, ease: [0.22, 1, 0.36, 1] }}
    >
      {visibleItems.length === 0 ? (
        <div className="orbit-feed-view orbit-feed-empty">
          <EditionEmptyState variant={emptyStateVariant} />
        </div>
      ) : (
        <OrbitFeedView
          items={filteredItems}
          localScoredArticles={isBackendMode ? [] : scoredArticles}
          profileName={activeProfile?.displayName}
          scanned={debugItems.length}
          decisionCounts={decisionCounts}
          activeFilters={activeFilters}
          onToggleFilter={toggleFilter}
          onResetFilters={resetFilters}
        />
      )}
    </motion.div>
  );
}
