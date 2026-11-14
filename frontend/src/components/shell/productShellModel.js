import { PRODUCT_NAV_ITEMS, getMobileNavItems } from "./navConfig";

// Decisions of the consumer shell (#463), kept out of the components so they
// can be tested in node. navConfig stays the single list of routes and labels;
// this module only decides how the new consumer chrome presents them.

// Part B §B6 orders the top bar feed, results, preferences, calibration. The
// Ops rail (ProductNav) still renders PRODUCT_NAV_ITEMS in its own order, so
// the consumer order is applied to a copy, never to the shared list.
const CONSUMER_ORDER = ["/", "/results", "/preferences", "/calibration"];

function rank(path) {
  const index = CONSUMER_ORDER.indexOf(path);
  return index === -1 ? CONSUMER_ORDER.length : index;
}

function inConsumerOrder(items) {
  // Array.prototype.sort is stable, so anything outside CONSUMER_ORDER (the
  // console entry) keeps its place at the end.
  return [...items].sort((a, b) => rank(a.path) - rank(b.path));
}

export function consumerNavItems() {
  return inConsumerOrder(PRODUCT_NAV_ITEMS);
}

// Phone navigation: the same destinations, plus the console entry only for a
// visitor who may enter the console (canEnterOpsShell, #54).
export function consumerDockItems({ isBackendMode, showConsoleEntry }) {
  return inConsumerOrder(getMobileNavItems("product", isBackendMode, { showConsoleEntry }));
}

// Pages already rebuilt in the new look render on the Signal UI ground. Every
// other consumer page keeps the Orbit token scope on its body, so its Orbit
// styling stays legible inside the new chrome until its own milestone-15 issue
// migrates it (#464 feed, #470 preferences/interests/calibration, #471
// results, #472 account). Migrating a page = adding its path here.
export const SIGNAL_SURFACE_PATHS = ["/", "/results", "/preferences", "/interests", "/calibration", "/account"];

export function pageSurface(pathname, migrated = SIGNAL_SURFACE_PATHS) {
  return migrated.includes(pathname) ? "signal" : "orbit";
}
