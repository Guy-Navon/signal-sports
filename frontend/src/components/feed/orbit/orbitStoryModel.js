import { getDecisionConfig } from "@/components/feed/decisionConfig";

const SOURCE_FALLBACK = "מקור לא ידוע";

export function orbitStoryId(item) {
  return item?.clusterId ?? item?.id ?? null;
}

export function orbitStoryTitle(item) {
  if (!item) return "";
  return item.type === "cluster"
    ? item.clusterTitle || item.translatedTitle || item.title || ""
    : item.translatedTitle || item.title || "";
}

export function orbitFeedbackArticleId(item, reports = []) {
  if (!item) return null;
  if (item.type !== "cluster") return item.id;
  const visiblePrimary = reports.find(
    (report) => report.articleId === item.primaryArticleId
  );
  return visiblePrimary?.articleId ?? reports[0]?.articleId ?? item.id;
}

function normalizeReport(report) {
  return {
    articleId: report.articleId ?? report.id,
    source: report.source,
    sourceDisplayName: report.sourceDisplayName ?? report.source ?? SOURCE_FALLBACK,
    title: report.translatedTitle ?? report.title ?? "",
    url: report.url ?? null,
    publishedAt: report.publishedAt ?? null,
    decision: report.decision ?? report.score?.decision ?? null,
  };
}

/**
 * Return consumer-visible reports only.
 *
 * Backend clusters already carry `members`, which is the authoritative visible
 * set. Local mode predates that payload, so its reports are hydrated from the
 * already-scored local article catalogue. A locally hidden/disabled article is
 * filtered out here and `suppressedMembers` is deliberately never read.
 */
export function orbitStoryReports(item, localScoredArticles = []) {
  if (!item) return [];
  if (item.type !== "cluster") return [normalizeReport(item)];

  if (Array.isArray(item.members) && item.members.length > 0) {
    return item.members
      .filter((member) => member?.decision !== "hidden")
      .map(normalizeReport);
  }

  const articleIds = new Set(item.articleIds ?? []);
  return localScoredArticles
    .filter(
      (article) =>
        articleIds.has(article.id) &&
        article.score?.decision &&
        article.score.decision !== "hidden"
    )
    .map(normalizeReport);
}

export function reportsWithPrimaryFirst(item, reports) {
  const primaryId = item?.primaryArticleId;
  if (!primaryId) return reports;
  return [...reports].sort((a, b) => {
    if (a.articleId === primaryId) return -1;
    if (b.articleId === primaryId) return 1;
    return 0;
  });
}

export function reportsChronologically(reports) {
  return [...reports].sort((a, b) => {
    const aTime = Date.parse(a.publishedAt ?? "") || 0;
    const bTime = Date.parse(b.publishedAt ?? "") || 0;
    return aTime - bTime;
  });
}

export function orbitSourceKey(report) {
  return report?.source ?? report?.sourceDisplayName?.trim().toLocaleLowerCase() ?? null;
}

export function uniqueOrbitSourceReports(reports) {
  const seen = new Set();
  return reports.filter((report) => {
    const key = orbitSourceKey(report);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function orbitUniqueSourceCount(reports) {
  return uniqueOrbitSourceReports(reports).length;
}

export function orbitHasMultiSourceField(item, reports) {
  if (item?.type !== "cluster") return false;
  const uniqueCount = orbitUniqueSourceCount(reports);
  const declaredCount = Number.isFinite(item.sourceCount)
    ? item.sourceCount
    : uniqueCount;
  return declaredCount >= 2 && uniqueCount >= 2;
}

export function detectNewSource(previousReports, nextReports) {
  const previousSources = new Set(previousReports.map(orbitSourceKey).filter(Boolean));
  return (
    nextReports.find((report) => {
      const source = orbitSourceKey(report);
      return source && !previousSources.has(source);
    }) ?? null
  );
}

export function orbitStorySourceLine(item, reports) {
  if (!item) return SOURCE_FALLBACK;
  if (item.type !== "cluster") {
    return item.sourceDisplayName ?? item.source ?? SOURCE_FALLBACK;
  }
  return (
    reports.find((report) => report.articleId === item.primaryArticleId)?.sourceDisplayName ??
    reports[0]?.sourceDisplayName ??
    item.sourceDisplayNames?.[0] ??
    SOURCE_FALLBACK
  );
}

export function orbitStoryTimestamp(item, reports = []) {
  if (!item) return null;
  if (item.type !== "cluster") return item.publishedAt ?? null;
  const latestVisibleTimestamp = reports.reduce((latest, report) => {
    const timestamp = Date.parse(report.publishedAt ?? "");
    return timestamp > latest.timestamp
      ? { timestamp, value: report.publishedAt }
      : latest;
  }, { timestamp: 0, value: null }).value;
  return latestVisibleTimestamp ?? item.publishedAt ?? item.firstSeenAt ?? null;
}

export function orbitStoryState(item) {
  const decision = item?.score?.decision ?? "feed";
  const config = getDecisionConfig(decision);
  return {
    decision,
    label: config.label,
    strength: config.strength,
    tone: config.tone,
  };
}

export function sourceInitial(sourceName) {
  const normalized = String(sourceName ?? "").trim();
  return normalized ? normalized[0].toUpperCase() : "•";
}

export function selectOrbitFocus(items) {
  return items[0] ?? null;
}

export function resolveOrbitFocus(items, selectedStoryId) {
  const selected = selectedStoryId
    ? items.find((item) => orbitStoryId(item) === selectedStoryId)
    : null;
  return {
    item: selected ?? selectOrbitFocus(items),
    isPinned: Boolean(selected),
  };
}

export function orbitQueueItems(items, focusItem) {
  const focusId = orbitStoryId(focusItem);
  return items.filter((item) => orbitStoryId(item) !== focusId);
}

/**
 * Presentation-only sanitization. Backend members are already visible-only;
 * local clusters are hydrated from scored articles. Replacing the cluster's
 * source metadata here keeps filters, freshness, feedback, and Orbit labels on
 * exactly that visible set without mutating AppContext's shared contract.
 */
export function prepareOrbitItems(items, localScoredArticles = []) {
  return items.map((item) => {
    if (item.type !== "cluster") return item;
    const reports = orbitStoryReports(item, localScoredArticles);
    const uniqueReports = uniqueOrbitSourceReports(reports);
    const visiblePrimary =
      reports.find((report) => report.articleId === item.primaryArticleId) ??
      reports[0] ??
      null;
    return {
      ...item,
      clusterTitle:
        visiblePrimary && visiblePrimary.articleId !== item.primaryArticleId
          ? visiblePrimary.title
          : item.clusterTitle,
      primaryArticleId: visiblePrimary?.articleId ?? item.primaryArticleId,
      members: reports,
      sources: uniqueReports.map((report) => report.source).filter(Boolean),
      sourceDisplayNames: uniqueReports.map((report) => report.sourceDisplayName),
      sourceCount: uniqueReports.length,
      lastUpdatedAt: orbitStoryTimestamp(item, reports),
    };
  });
}
