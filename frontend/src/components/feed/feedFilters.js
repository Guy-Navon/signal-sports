// Feed filter logic — extracted from Feed.jsx so behavior is locked by tests.
// Filter families share one active-filter Set:
//   levels  — decision levels, decision-level filters
//   topics  — content filters, topic and league filters
//   leagues — "league:<name>", toggled from the league pills of the new feed (#464)
//   sources — "source:<id>", any visible member source for a cluster (#483)
//   floor   — "min:<level>", an importance threshold from the filter bar (#483):
//             that level and above. At most one; ANDed with everything else.
// Filters only narrow what the engine already decided to show: every result is
// a subset of the visible items it was given, in the same order.
import { DECISION_CONFIG, DECISION_RANK } from "./decisionConfig";

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

const LEAGUE_PREFIX = "league:";
const SOURCE_PREFIX = "source:";

export const sourceFilterId = (source) => `${SOURCE_PREFIX}${source}`;

/** Authoritative visible members win over legacy source arrays. One entry per source. */
function filterSources(item) {
  const entries = item.type !== "cluster"
    ? [{ source: item.source, sourceDisplayName: item.sourceDisplayName }]
    : Array.isArray(item.members)
      ? item.members.filter((member) => (member.decision ?? member.score?.decision) !== "hidden")
      : (item.sources ?? []).map((source, index) => ({ source, sourceDisplayName: item.sourceDisplayNames?.[index] }));
  return [...new Map(entries.filter((entry) => entry.source).map((entry) => [
    sourceFilterId(entry.source), entry.sourceDisplayName ?? entry.source,
  ])).entries()];
}

export const itemSourceFilterIds = (item) => filterSources(item).map(([id]) => id);

/**
 * The one league filter an item belongs to (the league pills, #464): its league,
 * else "no league" within its sport, else plain "no league". A cluster reads the
 * league of its displayed article, like every other filter here.
 */
export function leagueFilterId(item) {
  if (item.league) return `${LEAGUE_PREFIX}${item.league}`;
  if (item.sport) return `${LEAGUE_PREFIX}none:${item.sport}`;
  return `${LEAGUE_PREFIX}none`;
}

const FLOOR_PREFIX = "min:";

/** The thresholds the filter bar offers: "רגיל ומעלה", "חשוב ומעלה" (#483). */
export const IMPORTANCE_FLOORS = ["feed", "high_feed"];

/** Commands, never stored: clear one family (toggleFilterSet). */
export const ALL_LEAGUES_ID = `${LEAGUE_PREFIX}*`;
export const ALL_LEVELS_ID = `${FLOOR_PREFIX}*`;
export const ALL_SOURCES_ID = `${SOURCE_PREFIX}*`;

export function importanceFilterId(level) {
  return `${FLOOR_PREFIX}${level}`;
}

const isFloorId = (filterId) => filterId.startsWith(FLOOR_PREFIX);
const isLeagueId = (filterId) => filterId.startsWith(LEAGUE_PREFIX);
const isSourceId = (filterId) => filterId.startsWith(SOURCE_PREFIX);
export const activeSourceIds = (activeFilters) => [...activeFilters].filter(isSourceId);

/** How many of these items a reader can see (never hidden or decision-less). */
export function visibleCount(items) {
  return items.filter((item) => meetsImportanceFloor(item, null)).length;
}

/** The active threshold level, or null for every level. */
export function importanceFloor(activeFilters) {
  for (const filterId of activeFilters) {
    if (isFloorId(filterId)) return filterId.slice(FLOOR_PREFIX.length);
  }
  return null;
}

/** The selected league pills, in selection order. */
export function activeLeagueIds(activeFilters) {
  return [...activeFilters].filter(isLeagueId);
}

export function hasActiveFilters(activeFilters) {
  return [...activeFilters].some((filterId) => filterId !== "all");
}

/**
 * At or above the floor (null: any visible level). Hidden and decision-less
 * items never pass, so a threshold can never reveal what the engine hid.
 */
export function meetsImportanceFloor(item, level) {
  const rank = DECISION_RANK[item.score?.decision] ?? 0;
  if (rank === 0) return false;
  return level == null || rank >= (DECISION_RANK[level] ?? Infinity);
}

export function itemMatchesFilter(item, filterId) {
  if (LEVEL_FILTER_IDS.includes(filterId)) return item.score?.decision === filterId;
  if (filterId.startsWith(LEAGUE_PREFIX)) return leagueFilterId(item) === filterId;
  if (isSourceId(filterId)) return filterSources(item).some(([id]) => id === filterId);
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

/**
 * AND across importance, league and source; OR within each multi-value facet.
 * Legacy exact-level/topic filters keep their OR semantics in their own group.
 * Every path rejects hidden/decision-less stories. Order and identities stay.
 */
export function filterFeedItems(visibleItems, activeFilters) {
  const active = activeFilters.has("all") ? [] : [...activeFilters];
  const floor = importanceFloor(new Set(active));
  const leagues = active.filter(isLeagueId);
  const sources = active.filter(isSourceId);
  const others = active.filter((f) => !isFloorId(f) && !isLeagueId(f) && !isSourceId(f));
  const matches = (item, family) => family.length === 0 || family.some((f) => itemMatchesFilter(item, f));
  return visibleItems.filter(
    (item) =>
      meetsImportanceFloor(item, floor) && matches(item, leagues) &&
      matches(item, sources) && matches(item, others)
  );
}

// Chip toggle semantics: "all" resets; empty selection falls back to "all".
// A floor replaces any other floor (choosing the same one clears it);
// ALL_LEAGUES_ID / ALL_LEVELS_ID clear only their own family.
export function toggleFilterSet(prev, chipId) {
  if (chipId === "all") return new Set(["all"]);
  const next = new Set(prev);
  next.delete("all");
  if (chipId === ALL_LEAGUES_ID || chipId === ALL_LEVELS_ID || chipId === ALL_SOURCES_ID) {
    const inFamily = chipId === ALL_LEAGUES_ID ? isLeagueId : chipId === ALL_SOURCES_ID ? isSourceId : isFloorId;
    for (const filterId of prev) if (inFamily(filterId)) next.delete(filterId);
  } else if (next.has(chipId)) {
    next.delete(chipId);
  } else {
    if (isFloorId(chipId)) for (const filterId of prev) if (isFloorId(filterId)) next.delete(filterId);
    next.add(chipId);
  }
  return next.size === 0 ? new Set(["all"]) : next;
}

const withoutFamily = (activeFilters, inFamily) => {
  const rest = [...activeFilters].filter((f) => f !== "all" && !inFamily(f));
  return new Set(rest.length ? rest : ["all"]);
};

/**
 * The importance control (#483): "הכול" then each threshold, with the number
 * of stories choosing it would show under the other active filters (faceted).
 * Labels come from DECISION_CONFIG, the one decision vocabulary (A3).
 */
export function importanceOptions(items, activeFilters) {
  const scope = filterFeedItems(items, withoutFamily(activeFilters, isFloorId)).filter((item) =>
    meetsImportanceFloor(item, null)
  );
  const floor = importanceFloor(activeFilters);
  return [
    { id: ALL_LEVELS_ID, level: null, label: "הכול", count: scope.length, selected: floor === null },
    ...IMPORTANCE_FLOORS.map((level) => ({
      id: importanceFilterId(level),
      level,
      label: `${DECISION_CONFIG[level].label} ומעלה`,
      count: scope.filter((item) => meetsImportanceFloor(item, level)).length,
      selected: floor === level,
    })),
  ];
}

/**
 * Per league filter id, how many stories pressing that pill would show under
 * the other active filters (the floor). Leagues with none are absent.
 */
export function facetedLeagueCounts(items, activeFilters) {
  const scope = filterFeedItems(items, withoutFamily(activeFilters, isLeagueId)).filter((item) =>
    meetsImportanceFloor(item, null)
  );
  const counts = new Map();
  for (const item of scope) {
    const id = leagueFilterId(item);
    counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  return counts;
}

/** Each cluster counts once per visible source, under the other active facets. */
export function facetedSourceCounts(items, activeFilters) {
  const scope = filterFeedItems(items, withoutFamily(activeFilters, isSourceId));
  const counts = new Map();
  for (const item of scope) {
    for (const [id] of filterSources(item)) counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  return counts;
}

/** Feed display names and stable whole-feed order, retaining selected zeros. */
export function sourceOptions(items, activeFilters) {
  const names = new Map();
  for (const item of items.filter((item) => meetsImportanceFloor(item, null))) {
    for (const [id, label] of filterSources(item)) if (!names.has(id)) names.set(id, label);
  }
  const totals = facetedSourceCounts(items, new Set(["all"]));
  const counts = facetedSourceCounts(items, activeFilters);
  for (const id of activeSourceIds(activeFilters)) if (!names.has(id)) names.set(id, id.slice(SOURCE_PREFIX.length));
  return [...names].sort(([a], [b]) => (totals.get(b) ?? 0) - (totals.get(a) ?? 0))
    .map(([id, label]) => ({ id, label, count: counts.get(id) ?? 0 }))
    .filter((option) => option.count > 0 || activeFilters.has(option.id));
}
