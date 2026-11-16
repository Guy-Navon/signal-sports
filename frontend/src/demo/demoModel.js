// The public read-only demo (#458): the live feed of profile "guy", exported
// hourly to static JSON by backend/scripts/export_demo_snapshot.py. Pure and
// node-tested. The demo makes no API calls: it reads static snapshot files only.
import { normalizeScoredArticleFromApi } from "@/api/normalizers";
import { getVisibleItems } from "@/components/feed/feedFilters";
import { formatUpdatedAgo } from "@/components/feed/feedFreshnessModel";
import { prepareFeedItems } from "@/components/feed/storyModel";
import { normalizeResultsResponse } from "@/components/results/resultsModel";

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
      .then(normalizeDemoResults)
      .catch(() => ({ games: [], details: {} })),
  ]);
  if (!Array.isArray(feed)) throw new Error("demo feed is not a list");
  const visible = getVisibleItems(feed.map(normalizeScoredArticleFromApi));
  return {
    meta,
    results: results.games,
    resultDetails: results.details,
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

// ---- Tabs (#553): the feed and the results, switched by the hash.

export const DEMO_TABS = [
  { id: "feed", label: "פיד", hash: "" },
  { id: "results", label: "תוצאות", hash: "#results" },
];

/** "#results" is the results tab; anything else (including no hash) is the feed. */
export function tabFromHash(hash) {
  return hash === "#results" ? "results" : "feed";
}

// Only exported, matching final-game details open a popup; no API calls.
export function normalizeDemoResults(raw) {
  const details = {};
  const games = normalizeResultsResponse(raw).games
    .filter(game => game.status === "final" || game.status === "scheduled")
    .map(game => {
      const detail = Object.hasOwn(raw?.details || {}, game.id) ? raw.details[game.id] : null;
      const available = game.status === "final" && game.detailAvailable
        && detail?.game_id === game.id && Array.isArray(detail?.players);
      if (available) details[game.id] = detail;
      return { ...game, detailAvailable: Boolean(available) };
    });
  return { games, details };
}
