import { PRODUCT_NAV_ITEMS } from "./navConfig";

// Decisions of the consumer shell (#463, navigation redesign #491), kept out of
// the components so they can be tested in node. navConfig stays the single list
// of routes and labels; this module only decides how the consumer chrome
// presents them.

// Part B §B6 orders the header feed, results, preferences, calibration. The
// Ops rail (ProductNav) still renders PRODUCT_NAV_ITEMS in its own order, so
// the consumer order is applied to a copy, never to the shared list.
const CONSUMER_ORDER = ["/", "/results", "/preferences", "/calibration"];

function rank(path) {
  const index = CONSUMER_ORDER.indexOf(path);
  return index === -1 ? CONSUMER_ORDER.length : index;
}

// Data-driven: whatever navConfig lists is rendered (a merged preferences +
// calibration destination may follow). Array.prototype.sort is stable, so an
// item outside CONSUMER_ORDER keeps its place after the known ones.
export function consumerNavItems(items = PRODUCT_NAV_ITEMS) {
  return [...items].sort((a, b) => rank(a.path) - rank(b.path));
}

// The consumer header draws its own icon set (#491): the shared navConfig icons
// also render in the Ops rail, which must not change. A destination with no
// key here falls back to its navConfig icon.
const CONSUMER_ICON_KEYS = {
  "/": "feed",
  "/results": "results",
  "/preferences": "preferences",
  "/calibration": "calibration",
};

export function consumerIconKey(path) {
  return CONSUMER_ICON_KEYS[path] ?? null;
}

// Collapse with hysteresis (#491). The masthead scrolls away in normal flow; a
// separate slim bar is shown once the masthead's tabs have FULLY left the top
// (ratio 0, above the bar line) and hidden only once they are FULLY back
// (ratio 1). Anything in between keeps the current state, so the bar never
// flickers at the threshold. `holding` (focus or an open menu inside the bar)
// keeps a shown bar shown, so focus is never dropped into an inert bar.
// `sample` comes from an IntersectionObserver entry; null keeps the state.
export function nextBarShown(shown, sample) {
  if (!sample) return shown;
  const { ratio, above, holding = false } = sample;
  if (!shown) return ratio === 0 && above === true;
  if (holding) return true;
  return ratio < 1;
}

const DATE_FORMAT = new Intl.DateTimeFormat("he-IL", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "Asia/Jerusalem",
});

// "שבת, 14 בנובמבר 2026": the masthead date line, in Israel time. ICU writes
// the weekday as "יום שבת"; the masthead drops "יום", as newspapers do.
export function mastheadDate(date) {
  return DATE_FORMAT.format(date).replace(/^יום\s+/, "");
}

// The avatar letter: the first character of the signed-in email. Without one
// the trigger draws a person icon instead.
export function accountInitial(user) {
  const first = user?.email?.trim()?.[0];
  return first ? first.toLocaleUpperCase("en-US") : null;
}

// Sections of the account menu, in order. "admin" (console entry, QA view-as,
// data mode) appears only for a visitor who may use those tools (#54).
export function accountMenuSections({ signedIn, showConsoleEntry, showSwitcher }) {
  const sections = [];
  if (signedIn) sections.push("account");
  sections.push("ground");
  if (showConsoleEntry || showSwitcher) sections.push("admin");
  if (signedIn) sections.push("signout");
  return sections;
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
