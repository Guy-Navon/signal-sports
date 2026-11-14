import { QUEUE_PAGE_SIZE } from "@/components/feed/queueMotion";
import { storyId } from "@/components/feed/storyModel";

// Feed motion (#467, docs/FRONTEND_DESIGN_SYSTEM.md B12). The motion itself is
// CSS (signal-feed.css); this module decides only what is bounded or
// data-driven: how long each element waits before entering, and which stories
// are new after a refresh.
//
// Bounded work (A5): the stagger is capped at ENTER_MAX_STEPS, so the page
// settles in the same time for 3 stories or 300, and removal is never animated
// (nothing here delays an unmount).

/** Milliseconds each stagger step adds. */
export const ENTER_STEP_MS = 40;

/** Hard cap on stagger steps, the shared queue budget of 6 (A5). */
export const ENTER_MAX_STEPS = 6;

/** The entrance itself (sg-enter in signal-feed.css), milliseconds. */
export const ENTER_DURATION_MS = 360;

/**
 * Where each part of the page starts on the first load, milliseconds: the page
 * builds top to bottom. After the first load every base is 0, so a filter
 * change or a new story enters at once.
 */
export const LOAD_SEQUENCE = Object.freeze({
  head: 0,
  pills: 60,
  lead: 90,
  important: 150,
  results: 200,
  stream: 240,
  side: 280,
});

/** The bases after the first load: everything enters at once. */
export const SETTLED_SEQUENCE = Object.freeze(
  Object.fromEntries(Object.keys(LOAD_SEQUENCE).map((key) => [key, 0]))
);

/**
 * Delay before element `index` of a section enters, milliseconds. Capped:
 * index 6 and index 198 wait the same.
 */
export function enterDelayMs(index, baseMs = 0) {
  const step = Number.isFinite(index) && index > 0 ? Math.min(index, ENTER_MAX_STEPS) : 0;
  return baseMs + step * ENTER_STEP_MS;
}

/** A bounded list restarts its stagger on each page ("show more"). */
export function pageStaggerIndex(index) {
  return Number.isFinite(index) && index > 0 ? index % QUEUE_PAGE_SIZE : 0;
}

/** The delay as a CSS custom property, read by the sg-enter rules. */
export function enterStyle(index, baseMs = 0) {
  return { "--sg-enter-delay": `${enterDelayMs(index, baseMs)}ms` };
}

/** Worst case for the first-load choreography to finish, milliseconds. */
export function loadSettleMs() {
  const latestBase = Math.max(...Object.values(LOAD_SEQUENCE));
  return latestBase + ENTER_MAX_STEPS * ENTER_STEP_MS + ENTER_DURATION_MS;
}

/** The ids of the given stories (cluster id first, as the rows key them). */
export function storyIdSet(items = []) {
  const ids = new Set();
  for (const item of items) {
    const id = storyId(item);
    if (id != null) ids.add(id);
  }
  return ids;
}

/**
 * Which stories to mark as new after the visible list changed.
 *
 * - The first list is a load, not a refresh: nothing is marked.
 * - Stories absent from the previous list are the arrivals; they replace the
 *   earlier arrivals.
 * - A refresh with nothing new keeps the earlier arrivals still present, so
 *   the mark does not vanish on an idle refetch.
 * - When more than half the list is new it is a different feed (a re-score
 *   after a preference change, another profile), not arrivals: nothing is
 *   marked.
 *
 * @param {{ previousIds: Set<string> | null, currentIds: Set<string>, previousArrivals: Set<string> }} args
 * @returns {Set<string>}
 */
export function nextArrivals({ previousIds, currentIds, previousArrivals }) {
  if (!previousIds || previousIds.size === 0) return new Set();
  const added = [...currentIds].filter((id) => !previousIds.has(id));
  if (added.length * 2 > currentIds.size) return new Set();
  if (added.length > 0) return new Set(added);
  return new Set([...previousArrivals].filter((id) => currentIds.has(id)));
}
