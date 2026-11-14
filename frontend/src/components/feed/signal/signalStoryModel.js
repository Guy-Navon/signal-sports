// Per-story values of the new feed rows (#464). Built on the shared story model so
// backend-authoritative cluster values are read, never re-derived (FRONTEND_DESIGN_SYSTEM
// A4): the source count is sourceCount, the members are storyReports.
import {
  sourceCount,
  reportsWithPrimaryFirst,
  uniqueSourceReports,
} from "@/components/feed/storyModel";

/**
 * Who reported a story: the authoritative count, and each visible member source
 * once (displayed member first) with the report to open for it.
 * @param {any} item
 * @param {Array<{ articleId: string, sourceDisplayName: string, url: string|null }>} reports
 *   from storyReports (visible members only)
 */
export function storySources(item, reports) {
  const unique = uniqueSourceReports(reportsWithPrimaryFirst(item, reports));
  const count = sourceCount(item, reports);
  return {
    count,
    multi: item?.type === "cluster" && count >= 2,
    names: unique.map((report) => report.sourceDisplayName),
    reports: unique,
  };
}

const publishedMs = (report) => {
  const at = Date.parse(report.publishedAt ?? "");
  return Number.isFinite(at) ? at : null;
};

/**
 * What a multi-source story opens to (#501): every visible report, not one per
 * source, because two reports from one site can say different things.
 *
 * Order: the displayed report (the one the headline opens) first, then the
 * others in the order they were published, oldest first, so the list reads as
 * the story's sequence of arrival; an undated report goes last. The displayed
 * report follows storyLink: the cluster's displayed member when visible, else
 * the first visible report.
 *
 * canOpen is false when the payload holds fewer than two reports: the story
 * then shows the source names only, rather than a list that cannot be filled.
 * @param {any} item
 * @param {Array<{ articleId: string, source?: string, sourceDisplayName: string, title: string, url: string|null, publishedAt: string|null }>} reports
 *   from storyReports (visible members only)
 */
export function clusterReportList(item, reports) {
  const seen = new Set();
  const unique = reports.filter((report) => {
    const key = report.articleId ?? report.url;
    if (key == null) return true;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const displayedId =
    unique.find((report) => report.articleId === item?.primaryArticleId)?.articleId ??
    unique[0]?.articleId;
  const displayed = unique.filter((report) => report.articleId === displayedId).slice(0, 1);
  const others = unique
    .filter((report) => !displayed.includes(report))
    .map((report, index) => ({ report, index, at: publishedMs(report) }))
    .sort((a, b) => {
      if (a.at === null || b.at === null) {
        return a.at === b.at ? a.index - b.index : a.at === null ? 1 : -1;
      }
      return a.at - b.at || a.index - b.index;
    })
    .map(({ report }) => report);
  const ordered = [...displayed, ...others].map((report) => ({
    ...report,
    displayed: report === displayed[0],
  }));
  const isCluster = item?.type === "cluster";
  return {
    reports: isCluster ? ordered : [],
    reportCount: isCluster ? ordered.length : 0,
    sourceCount: sourceCount(item, reports),
    canOpen: isCluster && ordered.length >= 2 && sourceCount(item, reports) >= 2,
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
