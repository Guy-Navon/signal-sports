// Shared by the dev-only feed labs (#464 feed, #467 motion). Nothing here
// reaches the main or demo bundles.
//
// case=real      the snapshot exactly as exported
// case=push      LAB FIXTURE: the first high_feed story re-marked as push
// case=push2     LAB FIXTURE: the first two high_feed stories re-marked as push
// case=pushlong  LAB FIXTURE: the story with the longest headline re-marked as push
// The fixtures only change a real story's decision, to see the lead block; the
// product never does this (no push, no lead).

export const LAB_CASES = {
  real: (items) => items,
  push: (items) => asPush(items, firstHighFeed(items, 1)),
  push2: (items) => asPush(items, firstHighFeed(items, 2)),
  pushlong: (items) => (items.length ? asPush(items, [longestTitle(items)]) : items),
};

export function labCaseName(value) {
  return LAB_CASES[value] ? value : "real";
}

function firstHighFeed(items, count) {
  return items.filter((item) => item.score?.decision === "high_feed").slice(0, count);
}

function longestTitle(items) {
  const title = (item) => item.translatedTitle || item.title || "";
  return items.reduce((longest, item) => (title(item).length > title(longest).length ? item : longest));
}

/** LAB FIXTURE ONLY: re-mark the given stories as push and rank them first. */
function asPush(items, chosen) {
  const ids = new Set(chosen.map((item) => item.id));
  const pushed = chosen.map((item) => ({ ...item, score: { ...item.score, decision: "push" } }));
  return [...pushed, ...items.filter((item) => !ids.has(item.id))];
}

// Feedback controls need the app context. Saves here go nowhere: they resolve
// after a short pause so the "saving / saved" states can be seen.
export const LAB_APP_CONTEXT = {
  addFeedback: () => new Promise((resolve) => setTimeout(resolve, 400)),
  neverShowArticle: () => new Promise((resolve) => setTimeout(resolve, 400)),
  isBackendMode: true,
  qaSurfaceAllowed: false,
  noteArticleOpened: () => {},
};
