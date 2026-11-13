// Per-story values of the new feed rows (#464). Built on the Orbit story model so
// backend-authoritative cluster values are read, never re-derived (FRONTEND_DESIGN_SYSTEM
// A4): the source count is orbitSourceCount, the members are orbitStoryReports.
import {
  orbitSourceCount,
  reportsWithPrimaryFirst,
  uniqueOrbitSourceReports,
} from "@/components/feed/orbit/orbitStoryModel";

/**
 * Who reported a story: the authoritative count, and each visible member source
 * once (displayed member first) with the report to open for it.
 * @param {any} item
 * @param {Array<{ articleId: string, sourceDisplayName: string, url: string|null }>} reports
 *   from orbitStoryReports (visible members only)
 */
export function storySources(item, reports) {
  const unique = uniqueOrbitSourceReports(reportsWithPrimaryFirst(item, reports));
  const count = orbitSourceCount(item, reports);
  return {
    count,
    multi: item?.type === "cluster" && count >= 2,
    names: unique.map((report) => report.sourceDisplayName),
    reports: unique,
  };
}

/** The article a story's headline opens: a cluster's displayed member, else its own url. */
export function storyLink(item, reports) {
  if (item?.type === "cluster") {
    return (
      reports.find((report) => report.articleId === item.primaryArticleId)?.url ??
      reports[0]?.url ??
      null
    );
  }
  return item?.url ?? null;
}

/**
 * Short Hebrew relative time, as in the approved mock ("לפני 12 דק׳", "אתמול").
 * Null for a missing or unreadable timestamp: no time is shown rather than a guess.
 */
export function relativeTimeHe(value, nowMs) {
  const at = value ? Date.parse(value) : NaN;
  if (!Number.isFinite(at)) return null;
  const minutesAgo = (nowMs - at) / 60_000;
  if (minutesAgo < 0) return "עכשיו";
  const minutes = Math.max(1, Math.round(minutesAgo));
  if (minutes < 60) return `לפני ${minutes} דק׳`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    if (hours === 1) return "לפני שעה";
    if (hours === 2) return "לפני שעתיים";
    return `לפני ${hours} שעות`;
  }
  const days = Math.round(hours / 24);
  if (days === 1) return "אתמול";
  if (days === 2) return "שלשום";
  return `לפני ${days} ימים`;
}

/**
 * Hebrew attaches a one-letter prefix to a Latin name or a number with a hyphen
 * ("ה-NBA", "ה-12"). Browsers may break the line after that hyphen, leaving "ה-"
 * alone at a line end (very visible in the lead headline). A word joiner after
 * the hyphen keeps the pair together; the visible text is unchanged.
 */
export function unbreakableHebrewPrefixes(title) {
  return String(title ?? "").replace(/(^|[\s"'(])([א-ת]{1,2})-(?=[A-Za-z0-9])/g, "$1$2-⁠");
}

/**
 * A title shown in its original foreign language (no Hebrew translation) takes
 * its own direction; Hebrew and translated titles follow the page (RTL), so a
 * Hebrew sentence that opens with an English name still reads right to left.
 */
export function titleDirection(item) {
  const translated = Boolean(item?.translatedTitle);
  const language = item?.language ?? "he";
  return !translated && language !== "he" ? "auto" : undefined;
}
