// Composition of the new feed (#464, docs/FRONTEND_DESIGN_SYSTEM.md B5-B10), as
// pure data. Placement only: nothing here re-ranks, re-scores or invents a level.
// Each section keeps the order it was given (the backend's ranking).
import {
  activeLeagueIds,
  activeSourceIds,
  facetedLeagueCounts,
  hasActiveFilters,
  importanceFloor,
  leagueFilterId,
  meetsImportanceFloor,
} from "@/components/feed/feedFilters";
import { DECISION_CONFIG } from "@/components/feed/decisionConfig";
import { LEAGUE_HE, SPORT_HE } from "@/components/feed/storyLabels";
import { storyReports, storyTimestamp } from "@/components/feed/storyModel";

/** The important row holds at most this many stories (B8). */
export const IMPORTANT_ROW_SIZE = 4;

const decisionOf = (item) => item?.score?.decision;

/**
 * lead       the first push, or null: no push means no lead block (B7)
 * important  further pushes, then high_feed, up to IMPORTANT_ROW_SIZE (B8)
 * stream     the rest of that list, then feed (B10)
 * brief      low_feed ("בקצרה", in the side column, #465)
 * Anything else (hidden, no decision) is placed nowhere.
 */
export function splitFeedSections(items) {
  const byDecision = { push: [], high_feed: [], feed: [], low_feed: [] };
  for (const item of items) {
    byDecision[decisionOf(item)]?.push(item);
  }
  const [lead = null, ...morePushes] = byDecision.push;
  const ranked = [...morePushes, ...byDecision.high_feed];
  return {
    lead,
    important: ranked.slice(0, IMPORTANT_ROW_SIZE),
    stream: [...ranked.slice(IMPORTANT_ROW_SIZE), ...byDecision.feed],
    brief: byDecision.low_feed,
  };
}

function leagueLabel(item) {
  if (item.league) return LEAGUE_HE[item.league] ?? item.league;
  return SPORT_HE[item.sport] ?? "אחר";
}

/**
 * The league pills (B6): one per league filter, with the number of stories that
 * selecting it shows. Highest count first; ties keep the order of first
 * appearance in the ranked feed.
 */
export function leaguePills(items) {
  const pills = new Map();
  for (const item of items) {
    if (!meetsImportanceFloor(item, null)) continue;
    const id = leagueFilterId(item);
    const pill = pills.get(id);
    if (pill) pill.count += 1;
    else pills.set(id, { id, label: leagueLabel(item), count: 1 });
  }
  // Array.prototype.sort is stable, so equal counts keep first-appearance order.
  return [...pills.values()].sort((a, b) => b.count - a.count);
}

/**
 * The league pills of the filter bar (#483): the order of the whole feed (so
 * pills never jump when the threshold changes), each count what pressing it
 * would show under the active threshold. A league with nothing at or above the
 * threshold is left out, unless it is selected (it must stay unselectable).
 */
export function filterBarPills(items, activeFilters) {
  const counts = facetedLeagueCounts(items, activeFilters);
  const selected = new Set(activeLeagueIds(activeFilters));
  return leaguePills(items)
    .map((pill) => ({ ...pill, count: counts.get(pill.id) ?? 0 }))
    .filter((pill) => pill.count > 0 || selected.has(pill.id));
}

/** "Showing X of N" while a filter is active; empty otherwise. */
export function filterResultLine(shown, total, activeFilters) {
  if (!hasActiveFilters(activeFilters)) return "";
  if (shown === 0) return "אין סיפורים שמתאימים לסינון";
  if (shown === 1) return `מוצג סיפור אחד מתוך ${total}`;
  return `מוצגים ${shown} מתוך ${total} סיפורים`;
}

/** The empty result names what was filtered (#483). */
export function filterEmptyMessage(activeFilters) {
  const floor = importanceFloor(activeFilters);
  const leagues = activeLeagueIds(activeFilters).length > 0;
  const sources = activeSourceIds(activeFilters).length > 0;
  const level = floor ? `ברמת ${DECISION_CONFIG[floor].label} ומעלה` : "";
  if (sources) return `אין סיפורים ${[level, leagues ? "בליגות שבחרת" : "", "במקורות שבחרת"].filter(Boolean).join(" ")}.`;
  if (floor && leagues) return `אין סיפורים ${level} בליגות שבחרת.`;
  if (floor) return `אין כרגע סיפורים ${level}.`;
  return "אין סיפורים בליגות שבחרת.";
}

/** The summary line (B6): "N סיפורים עברו את הסינון שלך · M חשובים". */
export function feedSummary(items) {
  let stories = 0;
  let important = 0;
  for (const item of items) {
    const decision = decisionOf(item);
    if (!decision || decision === "hidden") continue;
    stories += 1;
    if (decision === "push" || decision === "high_feed") important += 1;
  }
  return {
    stories,
    important,
    storiesPhrase: stories === 1 ? "סיפור עבר את הסינון שלך" : "סיפורים עברו את הסינון שלך",
    importantPhrase: important === 1 ? "חשוב" : "חשובים",
  };
}

/**
 * After "show more", keyboard focus moves to the first newly revealed row, so
 * the reader continues where the list grew. Null when nothing new appeared.
 */
export function showMoreFocusIndex(previousVisible, nextVisible) {
  return nextVisible > previousVisible ? previousVisible : null;
}

/** "אחרונים" in the side column holds at most this many stories (B11). */
export const LATEST_SIZE = 8;

const LATEST_DECISIONS = new Set(["push", "high_feed", "feed"]);
const FRESH_MS = 60 * 60_000;

/**
 * The side column's "אחרונים" (B11): the newest visible non-low_feed stories,
 * by the same timestamp the rows show (storyTimestamp, so a cluster's
 * backend update time wins). A read-only view of the list it is given: it never
 * adds a story, never touches the ranked order, and the same story may also
 * stand in the stream. A story with no readable time is left out here only.
 * Ties keep the ranked order (the sort is stable).
 * @param {any[]} items  the visible stories after the active filters
 * @param {{ localScoredArticles?: any[], limit?: number }} [options]
 */
export function latestStories(items, { localScoredArticles = [], limit = LATEST_SIZE } = {}) {
  return items
    .filter((item) => LATEST_DECISIONS.has(decisionOf(item)))
    .map((item) => ({
      item,
      at: Date.parse(storyTimestamp(item, storyReports(item, localScoredArticles)) ?? ""),
    }))
    .filter(({ at }) => Number.isFinite(at))
    .sort((a, b) => b.at - a.at)
    .slice(0, limit)
    .map(({ item }) => item);
}

/** A story under an hour old gets the fresh marker in "אחרונים" (B11). */
export function isFreshStory(timestamp, nowMs) {
  const at = timestamp ? Date.parse(timestamp) : NaN;
  return Number.isFinite(at) && nowMs - at < FRESH_MS;
}
