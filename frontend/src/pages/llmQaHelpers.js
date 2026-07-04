/**
 * Pure helper functions for the LLM QA page.
 * Exported for testability — no React or side effects.
 */

export const HEBREW_BROAD_SOURCES = ["walla_sport", "israel_hayom_sport", "ynet_sport"];

// Hebrew words that appear almost exclusively in football coverage in Israel.
// Used as a QA heuristic to flag basketball-classified articles for manual review.
// NOT product logic — never used in the relevance engine.
export const FOOTBALL_FALSE_POS_SIGNALS = [
  "כדורגל",
  "שוער",
  "שוערת",
  'בית"ר',
  "ביתר",
  "מכבי חיפה",
  "הפועל באר שבע",
  "מונדיאל",
  "פנאלטי",
  "גול",
];

/**
 * Returns true if the article looks like a possible football false-positive:
 * - from a Hebrew broad source
 * - classified as basketball
 * - title contains a football-signal word
 */
export function isPossibleFootballFalsePositive(article) {
  if (!HEBREW_BROAD_SOURCES.includes(article.source)) return false;
  if (article.sport !== "basketball") return false;
  const titleLower = (article.title || "").toLowerCase();
  return FOOTBALL_FALSE_POS_SIGNALS.some((signal) =>
    titleLower.includes(signal.toLowerCase())
  );
}

/**
 * Filter articles to the last 24 hours based on publishedAt.
 * Returns all articles if timeFilter is "all".
 */
export function filterByTimeWindow(articles, timeFilter) {
  if (timeFilter === "all") return articles;
  const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000);
  return articles.filter((a) => {
    const ts = new Date(a.publishedAt || 0);
    return ts >= cutoff;
  });
}

/**
 * Compute QA metrics from normalized debug feed items.
 * Only counts articles from HEBREW_BROAD_SOURCES.
 * Applies time filter; if the filtered result is empty, falls back to all-time
 * and sets usedFallback=true so the UI can warn the user.
 */
export function calcMetrics(debugItems, timeFilter) {
  const hebrewItems = debugItems.filter((a) =>
    HEBREW_BROAD_SOURCES.includes(a.source)
  );

  const filtered = filterByTimeWindow(hebrewItems, timeFilter);
  const usedFallback = filtered.length === 0 && hebrewItems.length > 0;
  const items = usedFallback ? hebrewItems : filtered;

  const total = items.length;
  const wallaCount = items.filter((a) => a.source === "walla_sport").length;
  const ihCount = items.filter(
    (a) => a.source === "israel_hayom_sport"
  ).length;
  const ynetCount = items.filter((a) => a.source === "ynet_sport").length;
  const visibleForGuy = items.filter(
    (a) => a.score?.decision !== "hidden"
  ).length;
  const hiddenForGuy = items.filter(
    (a) => a.score?.decision === "hidden"
  ).length;

  const classifiedByBreakdown = {};
  const sportBreakdown = {};
  const decisionBreakdown = {};

  for (const a of items) {
    const cb = a.classifiedBy || "rules";
    classifiedByBreakdown[cb] = (classifiedByBreakdown[cb] || 0) + 1;

    const sp = a.sport || "unknown";
    sportBreakdown[sp] = (sportBreakdown[sp] || 0) + 1;

    const d = a.score?.decision || "hidden";
    decisionBreakdown[d] = (decisionBreakdown[d] || 0) + 1;
  }

  return {
    total,
    wallaCount,
    ihCount,
    ynetCount,
    visibleForGuy,
    hiddenForGuy,
    unknownCount: sportBreakdown["unknown"] || 0,
    classifiedByBreakdown,
    sportBreakdown,
    decisionBreakdown,
    items,
    usedFallback,
  };
}

const DECISION_RANK = { push: 4, high_feed: 3, feed: 2, low_feed: 1, hidden: 0 };

/**
 * Build a Markdown QA summary string for clipboard export.
 */
export function buildQaSummary({
  timestamp,
  providerStatus,
  lastResetResult,
  ingestResults,
  metrics,
}) {
  const lines = [];

  lines.push("# Signal Sports — LLM QA Summary");
  lines.push(`Generated: ${timestamp}`);
  lines.push("");

  lines.push("## ספק סיווג");
  if (providerStatus) {
    lines.push(`- Provider: \`${providerStatus.provider}\``);
    lines.push(`- Model: \`${providerStatus.model || "—"}\``);
    lines.push(`- Can classify: ${providerStatus.can_classify}`);
    if (providerStatus.base_url)
      lines.push(`- Base URL: ${providerStatus.base_url}`);
  } else {
    lines.push("- לא נטען");
  }
  lines.push("");

  if (lastResetResult) {
    lines.push("## איפוס");
    lines.push(`- נמחקו כתבות: ${lastResetResult.deleted_articles}`);
    lines.push(
      `- נמחקו ריצות ייבוא: ${lastResetResult.deleted_ingestion_runs}`
    );
    lines.push("");
  }

  if (ingestResults && ingestResults.length > 0) {
    lines.push("## ייבוא");
    for (const r of ingestResults) {
      lines.push(
        `- ${r.source_id}: fetched=${r.fetched} inserted=${r.inserted} filtered=${r.skipped_filtered || 0} dup=${r.skipped_duplicate || 0} failed=${r.failed || 0}`
      );
    }
    lines.push("");
  }

  if (metrics) {
    lines.push("## מדדים (מקורות עברית בלבד)");
    lines.push(`- סה״כ כתבות: ${metrics.total}`);
    lines.push(`- וואלה ספורט: ${metrics.wallaCount}`);
    lines.push(`- ישראל היום: ${metrics.ihCount}`);
    lines.push(`- ynet ספורט: ${metrics.ynetCount || 0}`);
    lines.push(`- ניראה לגיא: ${metrics.visibleForGuy}`);
    lines.push(`- מוסתר לגיא: ${metrics.hiddenForGuy}`);
    lines.push(`- sport=unknown: ${metrics.unknownCount}`);
    lines.push("");

    lines.push("### פירוט classified_by");
    for (const [k, v] of Object.entries(metrics.classifiedByBreakdown)) {
      lines.push(`- ${k}: ${v}`);
    }
    lines.push("");

    lines.push("### פירוט ספורט");
    for (const [k, v] of Object.entries(metrics.sportBreakdown)) {
      lines.push(`- ${k}: ${v}`);
    }
    lines.push("");

    lines.push("### פירוט החלטות Guy");
    const sortedDecisions = Object.entries(metrics.decisionBreakdown).sort(
      (a, b) => (DECISION_RANK[b[0]] || 0) - (DECISION_RANK[a[0]] || 0)
    );
    for (const [k, v] of sortedDecisions) {
      lines.push(`- ${k}: ${v}`);
    }
    lines.push("");

    // Top visible articles
    const visible = (metrics.items || [])
      .filter((a) => a.score?.decision !== "hidden")
      .sort(
        (a, b) =>
          (DECISION_RANK[b.score?.decision] || 0) -
          (DECISION_RANK[a.score?.decision] || 0)
      )
      .slice(0, 15);
    if (visible.length > 0) {
      lines.push("### כתבות ניראות לגיא (עד 15)");
      for (const a of visible) {
        lines.push(
          `- [${a.score?.decision}] ${a.title} (${a.sport}/${a.league || "—"}) [${a.classifiedBy || "rules"}]`
        );
      }
      lines.push("");
    }

    // Still unknown
    const unknown = (metrics.items || [])
      .filter((a) => a.sport === "unknown")
      .slice(0, 10);
    if (unknown.length > 0) {
      lines.push("### עדיין לא מסווג — sport=unknown (עד 10)");
      for (const a of unknown) {
        lines.push(`- ${a.title} [${a.classifiedBy || "rules"}]`);
      }
      lines.push("");
    }

    // Football false positives
    const fps = (metrics.items || [])
      .filter(isPossibleFootballFalsePositive)
      .slice(0, 10);
    if (fps.length > 0) {
      lines.push("### חשד ל-false positive כדורגל→סל (עד 10)");
      for (const a of fps) {
        lines.push(
          `- ${a.title} (sport=${a.sport}) [${a.classifiedBy || "rules"}] reason: ${a.classificationReason || "—"}`
        );
      }
      lines.push("");
    }

    // LLM fallbacks
    const fallbacks = (metrics.items || [])
      .filter((a) => a.classifiedBy?.startsWith("rules_fallback_"))
      .slice(0, 10);
    if (fallbacks.length > 0) {
      lines.push("### LLM fallbacks (עד 10)");
      for (const a of fallbacks) {
        const conf =
          a.classificationConfidence != null
            ? `${Math.round(a.classificationConfidence * 100)}%`
            : "—";
        lines.push(`- ${a.title} [${a.classifiedBy}] confidence: ${conf}`);
      }
      lines.push("");
    }

    // Guardrail corrections
    const guardrails = (metrics.items || [])
      .filter((a) => a.classifiedBy === "llm+rules_guardrail")
      .slice(0, 10);
    if (guardrails.length > 0) {
      lines.push("### Guardrail corrections — LLM corrected by rules (עד 10)");
      for (const a of guardrails) {
        lines.push(
          `- ${a.title} (${a.sport}/${a.league || "—"}) reason: ${a.classificationReason || "—"}`
        );
      }
      lines.push("");
    }
  }

  return lines.join("\n");
}
