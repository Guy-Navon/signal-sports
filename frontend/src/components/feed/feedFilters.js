// Feed filter logic — extracted from Feed.jsx so behavior is locked by tests.

export const FILTER_CHIPS = [
  { id: "all", label: "הכל" },
  { id: "push", label: "דורש תשומת לב" },
  { id: "high_feed", label: "חשוב" },
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
  if (filterId === "push") return item.score?.decision === "push";
  if (filterId === "high_feed") return item.score?.decision === "high_feed";
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
