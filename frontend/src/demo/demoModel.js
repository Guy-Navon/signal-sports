// The public read-only demo (#458): the live feed of profile "guy", exported
// hourly to static JSON by backend/scripts/export_demo_snapshot.py. Pure and
// node-tested. The demo makes no API calls: these two files are all it reads.
import { normalizeScoredArticleFromApi } from "@/api/normalizers";
import { getVisibleItems } from "@/components/feed/feedFilters";
import { formatUpdatedAgo } from "@/components/feed/feedFreshnessModel";
import { prepareFeedItems } from "@/components/feed/orbit/orbitStoryModel";

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
 * Throws on a missing or malformed file, so the page can show its error state.
 * @param {(url: string, init?: { cache?: string }) => Promise<{ ok: boolean, status: number, json: () => Promise<any> }>} fetchImpl
 * @param {string} base  the site base path (import.meta.env.BASE_URL), ending in "/"
 */
export async function loadDemoSnapshot(fetchImpl, base = "/") {
  const [feed, meta] = await Promise.all([
    fetchJson(fetchImpl, `${base}demo-data/feed.json`),
    fetchJson(fetchImpl, `${base}demo-data/meta.json`),
  ]);
  if (!Array.isArray(feed)) throw new Error("demo feed is not a list");
  const visible = getVisibleItems(feed.map(normalizeScoredArticleFromApi));
  return {
    meta,
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

/** Per-level counts for the Orbit heading and filters (as Feed.jsx computes them). */
export function demoDecisionCounts(items) {
  const counts = { push: 0, high_feed: 0, feed: 0, low_feed: 0 };
  for (const item of items) {
    const decision = item.score?.decision;
    if (decision in counts) counts[decision] += 1;
  }
  return counts;
}
