// Feed filter logic — extracted from Feed.jsx so behavior is locked by tests.
// Two filter families share one active-filter Set:
//   levels — decision levels, toggled from the signal spectrum
//   topics — content filters, toggled from the quiet topic row

export const LEVEL_FILTER_IDS = ["push", "high_feed", "feed", "low_feed"];

export const TOPIC_CHIPS = [
  { id: "maccabi", label: "מכבי" },
  { id: "basketball", label: "כדורסל" },
  { id: "NBA", label: "NBA" },
  { id: "international", label: "מקורות מחו״ל" },
];

const INTL_SOURCES = ["sportando", "eurohoops"];

// Only non-hidden items appear in the main feed.
export function getVisibleItems(items) {
  return items.filter((item) => {
    const decision = item.score?.decision;
    return decision && decision !== "hidden";
  });
}

export function itemMatchesFilter(item, filterId) {
  if (LEVEL_FILTER_IDS.includes(filterId)) return item.score?.decision === filterId;
  if (filterId === "maccabi") {
    const entities = item.entities || [];
    const tags = item.tags || [];
    return (
      entities.some((e) => e.toLowerCase().includes("maccabi")) ||
      tags.some((t) => t.includes("מכבי"))
    );
  }
  if (filterId === "basketball") return item.sport === "basketball";
  if (filterId === "NBA") return item.league === "NBA";
  if (filterId === "international") {
    return item.type === "cluster"
      ? item.sources?.some((s) => INTL_SOURCES.includes(s))
      : INTL_SOURCES.includes(item.source);
  }
  return true;
}

export function filterFeedItems(visibleItems, activeFilters) {
  if (activeFilters.has("all")) return visibleItems;
  return visibleItems.filter((item) =>
    [...activeFilters].some((f) => itemMatchesFilter(item, f))
  );
}

// Chip toggle semantics: "all" resets; empty selection falls back to "all".
export function toggleFilterSet(prev, chipId) {
  if (chipId === "all") return new Set(["all"]);
  const next = new Set(prev);
  next.delete("all");
  if (next.has(chipId)) {
    next.delete(chipId);
  } else {
    next.add(chipId);
  }
  return next.size === 0 ? new Set(["all"]) : next;
}
