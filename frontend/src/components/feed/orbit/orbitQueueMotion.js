// Queue motion budget.
//
// The queue can hold every visible story (198 for Guy on the current corpus), so
// its animation strategy has to be *bounded*: total settle time must not grow
// with the number of cards.
//
// Two rules make that true:
//
//   1. The enter stagger is capped. Card N waits `min(N, MAX_STAGGER_STEPS)`
//      steps, never `N` steps — so the last card of a 200-item list starts at
//      the same moment as the last card of a 10-item list.
//   2. Removal is not animated at all. Filtering unmounts non-matching cards
//      synchronously, so a card that no longer matches can never linger.
//
// The previous strategy (`delay: index * 0.025` inside `AnimatePresence`) broke
// both: card 196 began animating 4.9s after a filter click, and exiting cards
// stayed mounted for the duration. Filtering 198 -> 20 left 197 stale cards on
// screen for 4-8s while the header already read "20 results".

/** Seconds each stagger step adds. */
export const QUEUE_STAGGER_STEP_S = 0.018;

/** Hard cap on stagger steps — this is what makes settle time constant. */
export const QUEUE_STAGGER_MAX_STEPS = 6;

/** Enter transition duration, seconds. */
export const QUEUE_ENTER_DURATION_S = 0.26;

/** Reduced-motion enter duration, seconds. */
export const QUEUE_REDUCED_DURATION_S = 0.1;

/** How many queue cards render before "show more". Bounds per-frame layout cost. */
export const QUEUE_PAGE_SIZE = 40;

/**
 * Delay before card `index` starts animating in, in seconds.
 * Capped at QUEUE_STAGGER_MAX_STEPS steps regardless of list length.
 */
export function queueEnterDelay(index, reduce = false) {
  if (reduce) return 0;
  if (!Number.isFinite(index) || index <= 0) return 0;
  return Math.min(index, QUEUE_STAGGER_MAX_STEPS) * QUEUE_STAGGER_STEP_S;
}

/**
 * Worst-case seconds for a list of `count` cards to finish animating in.
 * Constant for any count past the stagger cap — this is the property the
 * filtering fix depends on, and it is locked by orbitQueueMotion.test.js.
 */
export function queueSettleSeconds(count, reduce = false) {
  if (!Number.isFinite(count) || count <= 0) return 0;
  const duration = reduce ? QUEUE_REDUCED_DURATION_S : QUEUE_ENTER_DURATION_S;
  return queueEnterDelay(count - 1, reduce) + duration;
}

/** Framer-motion transition for a queue card. No layout spring: see module note. */
export function queueEnterTransition(index, reduce = false) {
  return {
    duration: reduce ? QUEUE_REDUCED_DURATION_S : QUEUE_ENTER_DURATION_S,
    delay: queueEnterDelay(index, reduce),
    ease: [0.22, 1, 0.36, 1],
  };
}

/** Initial/animate pair for a queue card. */
export function queueEnterMotion(reduce = false) {
  return reduce
    ? { initial: { opacity: 0 }, animate: { opacity: 1 } }
    : { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 } };
}

/**
 * How many cards to render, and whether more remain.
 * Keeps the animating/laid-out node count bounded no matter how large the feed.
 */
export function queuePage(total, shownPages = 1) {
  const safeTotal = Number.isFinite(total) && total > 0 ? total : 0;
  const pages = Number.isFinite(shownPages) && shownPages > 0 ? shownPages : 1;
  const visible = Math.min(safeTotal, pages * QUEUE_PAGE_SIZE);
  return { visible, remaining: safeTotal - visible, hasMore: safeTotal > visible };
}
