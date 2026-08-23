// Focus decisions for the Orbit field, as pure data.
//
// These used to be inlined in OrbitFeedView alongside `document.querySelector`
// lookups and `cores[cores.length - 1]` — the index existed only because
// AnimatePresence keeps an exiting core mounted, so "the last one in the DOM"
// happened to be the incoming one. That coupled keyboard behaviour to CSS class
// names and animation internals, and nothing tested it.
//
// The component now holds refs to the real elements, so *which* node to focus is
// no longer a question. What remains is *when* and *what* — decided here, in
// functions that run under plain node.

/** Focusable roles the field exposes. */
export const FOCUS_TARGETS = Object.freeze({
  core: "core",
  primaryAction: "primaryAction",
  closeAction: "closeAction",
});

/** Desktop keeps the field in view on its own; narrower layouts must scroll. */
export const FIELD_SCROLL_MAX_WIDTH = 1200;

/** When an intent should pull the field into view. */
export const SCROLL_POLICY = Object.freeze({
  never: "never",
  ifNarrow: "ifNarrow",
  always: "always",
});

/**
 * Should focusing a story scroll the field into view?
 * At >=1200px the field is a sticky column already on screen, so scrolling it
 * would yank the page for no reason.
 */
export function shouldScrollFieldIntoView(viewportWidth) {
  if (!Number.isFinite(viewportWidth)) return false;
  return viewportWidth < FIELD_SCROLL_MAX_WIDTH;
}

/** Resolve a policy against the live viewport. */
export function shouldScrollForIntent(policy, viewportWidth) {
  if (policy === SCROLL_POLICY.always) return true;
  if (policy === SCROLL_POLICY.ifNarrow) return shouldScrollFieldIntoView(viewportWidth);
  return false;
}

/**
 * A queue story was chosen: the field now shows it, collapsed.
 * Focus follows the reader into the core. On stacked layouts the field is below
 * the queue, so it has to be scrolled to; on desktop it is already beside it.
 */
export function focusIntentForStorySelection() {
  return {
    target: FOCUS_TARGETS.core,
    collapse: true,
    scrollField: SCROLL_POLICY.ifNarrow,
  };
}

/**
 * The cluster was opened: focus moves to the control that closes it again.
 * Expansion replaces the whole layout, so the field is always scrolled to.
 */
export function focusIntentForExpand() {
  return { target: FOCUS_TARGETS.closeAction, scrollField: SCROLL_POLICY.always };
}

/** The cluster was closed: focus returns to the control that opened it. */
export function focusIntentForCollapse() {
  return { target: FOCUS_TARGETS.primaryAction, scrollField: SCROLL_POLICY.never };
}

/**
 * The focused story changed underneath us — a filter or a refresh replaced it,
 * rather than the reader picking one.
 *
 * An expanded field must not survive that: it would be showing the sources of a
 * story that is no longer in focus. If the story being expanded is the one that
 * went away, the reader's focus was inside that subtree, so it has to be moved
 * somewhere real; otherwise leave focus where the reader put it.
 */
export function resolveStoryChange({ previousStoryId, nextStoryId, expandedStoryId }) {
  if (!previousStoryId || previousStoryId === nextStoryId) {
    return { collapse: false, target: null, scrollField: SCROLL_POLICY.never };
  }
  return {
    collapse: Boolean(expandedStoryId),
    target: expandedStoryId === previousStoryId ? FOCUS_TARGETS.core : null,
    // The reader did not ask for this, so do not move the page under them.
    scrollField: SCROLL_POLICY.never,
  };
}

/**
 * Is this expansion state real? `expandedStoryId` is remembered across renders,
 * so it can point at a story that has since been filtered out.
 */
export function isFieldExpanded(activeStoryId, expandedStoryId) {
  return Boolean(activeStoryId) && activeStoryId === expandedStoryId;
}
