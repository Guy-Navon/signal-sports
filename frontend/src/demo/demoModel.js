// The public read-only demo (#458): the live feed of profile "guy", exported
// hourly to static JSON by backend/scripts/export_demo_snapshot.py. Pure and
// node-tested. The demo makes no API calls: it reads static snapshot files only.
import { normalizeScoredArticleFromApi } from "@/api/normalizers";
import { getVisibleItems } from "@/components/feed/feedFilters";
import { formatUpdatedAgo } from "@/components/feed/feedFreshnessModel";
import { prepareFeedItems } from "@/components/feed/storyModel";
import { normalizeResultsResponse } from "@/components/results/resultsModel";
import { dateChips, followedTeamIds, streamDays, summaryParts, tileVerdict, TILE_LIMIT } from "@/components/results/resultsLayoutModel";

// The worker runs every few minutes and the export every hour, so anything
// older than this means the pipeline or the owner's PC has stopped.
export const DEMO_STALE_AFTER_MINUTES = 180;

const STALE_WARNING = "הנתונים בהדגמה לא התעדכנו כבר כמה שעות";
const UNKNOWN_TIME = "זמן העדכון לא ידוע";

async function fetchJson(fetchImpl, url) {
  const response = await fetchImpl(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`demo data ${url} failed: ${response.status}`);
  return response.json();
}

/**
 * Load the snapshot and shape it exactly as the real app shapes /api/me/feed:
 * normalizeScoredArticleFromApi, visible items only, backend-mode preparation.
 * Throws on a missing or malformed feed/meta file. Results are optional: an
 * older snapshot or a broken results file leaves the feed usable with no strip.
 * @param {(url: string, init?: { cache?: string }) => Promise<{ ok: boolean, status: number, json: () => Promise<any> }>} fetchImpl
 * @param {string} base  the site base path (import.meta.env.BASE_URL), ending in "/"
 */
export async function loadDemoSnapshot(fetchImpl, base = "/") {
  const [feed, meta, results] = await Promise.all([
    fetchJson(fetchImpl, `${base}demo-data/feed.json`),
    fetchJson(fetchImpl, `${base}demo-data/meta.json`),
    fetchJson(fetchImpl, `${base}demo-data/results.json`)
      .then((raw) => normalizeResultsResponse(raw).games.map(scoresOnlyGame))
      .catch(() => []),
  ]);
  if (!Array.isArray(feed)) throw new Error("demo feed is not a list");
  const visible = getVisibleItems(feed.map(normalizeScoredArticleFromApi));
  return {
    meta,
    results,
    items: prepareFeedItems(visible, { isBackendMode: true, localScoredArticles: [] }),
  };
}

/**
 * The banner line: when the pipeline last refreshed the feed (the export time
 * when no cycle time is known), and a plain warning once that is too old.
 * @param {{ last_successful_cycle_at?: string|null, generated_at?: string|null }|null} meta
 * @param {number} nowMs
 */
export function demoBanner(meta, nowMs) {
  const stamp = meta?.last_successful_cycle_at || meta?.generated_at;
  const parsed = stamp ? Date.parse(stamp) : NaN;
  if (!Number.isFinite(parsed)) {
    return { updated: UNKNOWN_TIME, stale: true, warning: STALE_WARNING };
  }
  const ageMinutes = Math.max(0, (nowMs - parsed) / 60_000);
  const stale = ageMinutes > DEMO_STALE_AFTER_MINUTES;
  return { updated: formatUpdatedAgo(ageMinutes), stale, warning: stale ? STALE_WARNING : null };
}

/** Per-level counts for the feed summary and filters (as Feed.jsx computes them). */
export function demoDecisionCounts(items) {
  const counts = { push: 0, high_feed: 0, feed: 0, low_feed: 0 };
  for (const item of items) {
    const decision = item.score?.decision;
    if (decision in counts) counts[decision] += 1;
  }
  return counts;
}

// ---- Tabs (#553): the feed and the scores-only results, switched by the hash.

export const DEMO_TABS = [
  { id: "feed", label: "פיד", hash: "" },
  { id: "results", label: "תוצאות", hash: "#results" },
];

/** "#results" is the results tab; anything else (including no hash) is the feed. */
export function tabFromHash(hash) {
  return hash === "#results" ? "results" : "feed";
}

// ---- Results, scores only (#526, #553).

/**
 * The only fields of a game the public demo keeps. The exporter already
 * projects onto this allowlist; this is the second line of defence, so even a
 * richer file can never put leaders, chosen-player lines, ranks, venue or
 * attendance on the page.
 */
export function scoresOnlyGame(game) {
  const side = (s) => ({ id: s?.id ?? null, name: s?.name ?? "", nameProvider: s?.name ?? "", score: s?.score ?? null, isWinner: Boolean(s?.isWinner), rank: null });
  return {
    id: game.id,
    competitionId: game.competitionId,
    competitionHe: game.competitionHe,
    competitionEn: game.competitionEn,
    sport: game.sport,
    status: game.status,
    startTime: game.startTime,
    localDate: game.localDate,
    winner: game.winner,
    relevanceReason: game.relevanceReason || "",
    home: side(game.home),
    away: side(game.away),
    leaders: [],
    chosenPlayerLines: [],
    detailAvailable: false,
  };
}

const FOLLOWED_REASON = /^followed_team:(team:.+)$/;
const startMs = (game) => Date.parse(game.startTime) || 0;

/**
 * Everything the demo results view renders, from the exported games. Tiles are
 * the newest finals whose relevance_reason is followed_team:<id>, at most four.
 * Upcoming games are not exported, so there is no tonight box.
 * @param {any[]} games  scoresOnlyGame output
 * @param {Date} now
 */
export function demoResultsView(games, now = new Date()) {
  const finals = (games || []).filter((game) => game.status === "final");
  if (finals.length === 0) return { state: "empty", summary: [], tiles: [], chips: [], days: [], followed: new Set() };
  const followed = followedTeamIds(null, finals);
  const tiles = finals
    .filter((game) => FOLLOWED_REASON.test(game.relevanceReason))
    .sort((a, b) => startMs(b) - startMs(a) || a.id.localeCompare(b.id))
    .slice(0, TILE_LIMIT)
    .map((game) => ({ game, verdict: tileVerdict(game, followed), chosen: null }));
  return {
    state: "ready",
    followed,
    tiles,
    summary: summaryParts(finals, now),
    chips: dateChips(finals, now),
    days: streamDays(finals, followed, now),
  };
}
