import React, { useState, useMemo } from "react";
import { Rss, SlidersHorizontal } from "lucide-react";
import { useApp } from "@/context/AppContext";
import ArticleCard from "@/components/feed/ArticleCard";
import FeedHero from "@/components/feed/FeedHero";
import FeedHeader from "@/components/feed/FeedHeader";
import FilterChips from "@/components/feed/FilterChips";
import EmptyState from "@/components/shared/EmptyState";
import LoadingSkeleton from "@/components/shared/LoadingSkeleton";
import {
  getVisibleItems,
  filterFeedItems,
  toggleFilterSet,
  itemMatchesFilter,
} from "@/components/feed/feedFilters";

export default function Feed() {
  const { feedItems, activeProfile, isBackendMode, isLoading } = useApp();
  const [activeFilters, setActiveFilters] = useState(new Set(["all"]));

  const visibleItems = useMemo(() => getVisibleItems(feedItems), [feedItems]);

  const decisionCounts = useMemo(() => {
    const c = { push: 0, high_feed: 0, feed: 0, low_feed: 0 };
    for (const item of visibleItems) {
      const d = item.score?.decision;
      if (d in c) c[d] += 1;
    }
    return c;
  }, [visibleItems]);

  // Counts per filter chip for the quiet badges.
  const filterCounts = useMemo(() => {
    const ids = ["push", "high_feed", "maccabi", "basketball", "NBA", "international"];
    const counts = {};
    for (const id of ids) {
      counts[id] = visibleItems.filter((i) => itemMatchesFilter(i, id)).length;
    }
    return counts;
  }, [visibleItems]);

  const filteredItems = useMemo(
    () => filterFeedItems(visibleItems, activeFilters),
    [visibleItems, activeFilters]
  );

  const isUnfiltered = activeFilters.has("all");

  // Hero: the single most relevant story, only in the unfiltered view.
  const heroEligible =
    isUnfiltered &&
    filteredItems.length > 0 &&
    ["push", "high_feed"].includes(filteredItems[0].score?.decision);
  const heroItem = heroEligible ? filteredItems[0] : null;
  const listItems = heroItem ? filteredItems.slice(1) : filteredItems;

  const toggleFilter = (chipId) => setActiveFilters((prev) => toggleFilterSet(prev, chipId));

  // Loading state (backend mode, first fetch)
  if (isBackendMode && isLoading && visibleItems.length === 0) {
    return (
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="h-9 w-40 rounded-md bg-surface-2 animate-pulse" />
        <LoadingSkeleton variant="card" count={4} />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <FeedHeader
        profileName={activeProfile?.displayName}
        total={visibleItems.length}
        counts={decisionCounts}
      />

      <FilterChips activeFilters={activeFilters} onToggle={toggleFilter} counts={filterCounts} />

      {filteredItems.length === 0 ? (
        visibleItems.length === 0 ? (
          <EmptyState
            icon={Rss}
            title="אין סיגנלים חדשים"
            hint="הפיד יתעדכן כשיגיעו סיפורים רלוונטיים לפרופיל שלך."
          />
        ) : (
          <EmptyState
            icon={SlidersHorizontal}
            title="אין פריטים תואמים לסינון"
            hint="נסה להסיר חלק מהמסננים כדי לראות יותר סיפורים."
            action={
              <button
                onClick={() => toggleFilter("all")}
                className="text-sm text-signal-high hover:text-signal-high/80 transition-colors"
              >
                הצג הכל
              </button>
            }
          />
        )
      ) : (
        <div className="space-y-3">
          {heroItem && <FeedHero item={heroItem} />}
          {listItems.map((item, i) => (
            <ArticleCard key={item.id} item={item} index={heroItem ? i + 1 : i} />
          ))}
        </div>
      )}
    </div>
  );
}
