/**
 * Normalizers: backend snake_case API responses → frontend camelCase shapes.
 *
 * The frontend engine and UI components use camelCase field names throughout.
 * These normalizers are the single place where the translation happens so that
 * no component needs to know about the backend naming convention.
 */

export function normalizeArticleFromApi(a) {
  return {
    id: a.id,
    source: a.source,
    sourceDisplayName: a.source_display_name ?? a.source,
    url: a.url,
    title: a.title,
    originalTitle: a.original_title ?? null,
    translatedTitle: a.translated_title ?? null,
    language: a.language ?? "he",
    publishedAt: a.published_at,
    sport: a.sport,
    league: a.league ?? null,
    entities: a.entities ?? [],
    eventType: a.event_type,
    importance: a.importance,
    confidence: a.confidence ?? 0.85,
    tags: a.tags ?? [],
    clusterId: a.cluster_id ?? null,
    subtitle: a.subtitle ?? null,
    classifiedBy: a.classified_by ?? "rules",
    classificationProvider: a.classification_provider ?? null,
    classificationReason: a.classification_reason ?? null,
    classificationConfidence: a.classification_confidence ?? null,
    // ArticleFacts classification trace (issue #35 — Debug facts panels).
    classificationTrace: a.classification_trace ?? null,
  };
}

function normalizeTopicPreferenceFromApi(t) {
  return {
    topicId: t.topic_id,
    label: t.label,
    sport: t.sport,
    priority: t.priority,
    mode: t.mode,
    scope: t.scope ?? null,
    leagues: t.leagues ?? [],
    entities: t.entities ?? [],
    eventRules: t.event_rules ?? {},
    entityEventRules: t.entity_event_rules ?? null,
    mutedSubtopics: t.muted_subtopics ?? [],
  };
}

export function normalizeProfileFromApi(p) {
  return {
    userId: p.user_id,
    displayName: p.display_name,
    language: p.language ?? "he",
    profileType: p.profile_type,
    mutedTopics: p.muted_topics ?? [],
    mutedSources: p.muted_sources ?? [],
    followedEntities: p.followed_entities ?? [],
    topics: (p.topics ?? []).map(normalizeTopicPreferenceFromApi),
    // ProfileV2 affinity payload (issue #83 — provenance display in the
    // Preferences interests tab). Kept in wire shape: consumers read
    // scope_affinities/event_affinities fields directly.
    profileV2: p.profile_v2 ?? null,
  };
}

/**
 * Normalize a backend ScoredArticle into a feed item compatible with FeedCard
 * and DebugRow. The article fields are flattened to the top level, and a `score`
 * sub-object is added that matches the shape returned by the frontend engine:
 *   { decision, matchedTopic, matchedRule, reasoning }
 *
 * Note: the backend field `matched_event_rule` maps to `matchedRule` (not
 * `matchedEventRule`) to stay consistent with the frontend engine's output shape
 * which Debug.jsx already reads via `item.score?.matchedRule`.
 */
function normalizeClusterMemberFromApi(m) {
  return {
    articleId: m.article_id,
    source: m.source,
    sourceDisplayName: m.source_display_name ?? m.source,
    title: m.title,
    url: m.url,
    publishedAt: m.published_at,
    decision: m.decision,
  };
}

export function normalizeScoredArticleFromApi(sa) {
  const article = normalizeArticleFromApi(sa.article);
  const score = {
    decision: sa.decision,
    label: DECISION_LABELS_HE[sa.decision] ?? sa.decision,
    matchedTopic: sa.matched_topic ?? null,
    matchedRule: sa.matched_event_rule ?? null,
    reasoning: sa.reasoning ?? [],
    // Preference V2 structured trace + engine badge (issues #32/#35).
    contributions: sa.contributions ?? null,
    engine: sa.engine ?? null,
  };

  // Story clustering (#104). The backend attaches `cluster` to the DISPLAYED member only.
  // We map it onto the pre-existing `type: "cluster"` item contract the UI already speaks,
  // so LeadStory / StreamRow / BriefsDigest / Debug need no new item shape.
  //
  // Two decisions live here and must not be confused:
  //   score.decision       = the CARD decision (MAX over this user's VISIBLE members)
  //   articleScoreDecision = the DISPLAYED ARTICLE's own decision (unchanged by clustering)
  // The card ranks by the former; Debug shows both.
  const c = sa.cluster;
  if (!c) return { ...article, type: "article", score };

  const members = (c.members ?? []).map(normalizeClusterMemberFromApi);
  const suppressedMembers = (c.suppressed_members ?? []).map(normalizeClusterMemberFromApi);

  return {
    ...article,                       // the displayed member's article fields (url, source, …)
    type: "cluster",
    clusterId: c.cluster_id,
    clusterTitle: article.translatedTitle || article.title,
    // Roles — may be three different articles (docs/CLUSTERING.md §9).
    primaryArticleId: c.displayed_article_id,
    representativeArticleId: c.representative_article_id ?? null,
    priorityArticleId: c.priority_article_id,
    displayedReason: c.displayed_reason,
    // VISIBLE members only. Suppressed members never appear in the consumer payload.
    sourceCount: c.source_count,
    members,
    articleIds: members.map(m => m.articleId),
    sources: members.map(m => m.source),
    sourceDisplayNames: members.map(m => m.sourceDisplayName),
    // Debug-only; the backend leaves this empty for the consumer feed.
    suppressedMembers,
    // Update timestamp comes from the newest VISIBLE member — never a hidden one.
    lastUpdatedAt: c.sort_at,
    firstSeenAt: members.length
      ? members[members.length - 1].publishedAt
      : article.publishedAt,
    ruleVersion: c.rule_version ?? null,
    eventState: c.event_state ?? null,
    // The CARD decision drives ranking and the level chip.
    score: {
      ...score,
      decision: c.decision,
      label: DECISION_LABELS_HE[c.decision] ?? c.decision,
    },
    // The displayed article's OWN decision — preserved so Debug can prove clustering
    // caused no article-level drift.
    articleScoreDecision: sa.decision,
  };
}

// ── Ingestion result normalizer ───────────────────────────────────────────────

export function normalizeIngestResultFromApi(r) {
  return {
    sourceId: r.source_id,
    fetched: r.fetched ?? 0,
    inserted: r.inserted ?? 0,
    skippedDuplicate: r.skipped_duplicate ?? 0,
    skippedFiltered: r.skipped_filtered ?? 0,
    failed: r.failed ?? 0,
    errors: r.errors ?? [],
    // Timing fields (null when not measured — e.g., source not found or fetch error)
    fetchMs: r.fetch_ms ?? null,
    totalMs: r.total_ms ?? null,
    llmAttempts: r.llm_attempts ?? 0,
    llmSuccesses: r.llm_successes ?? 0,
    llmFallbackConnectError: r.llm_fallback_connect_error ?? 0,
    llmFallbackTimeoutOrParse: r.llm_fallback_timeout_or_parse ?? 0,
    llmFallbackLowConfidence: r.llm_fallback_low_confidence ?? 0,
    llmAvgMs: r.llm_avg_ms ?? null,
    llmP95Ms: r.llm_p95_ms ?? null,
    // Gating fields: eligible articles skipped by gate and why (live response only).
    llmSkipped: r.llm_skipped ?? 0,
    llmSkipReasons: r.llm_skip_reasons ?? {},
    llmCallReasons: r.llm_call_reasons ?? {},
  };
}

// ── Timing format helpers ─────────────────────────────────────────────────────

/**
 * Format a duration in ms as "420ms" (< 1000ms) or "2.9s" (>= 1000ms).
 * Returns "—" for null/undefined.
 */
export function formatMs(ms) {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Format a total run duration in ms.
 * >= 60 000ms → "1:44" (minutes:seconds)
 * < 60 000ms  → "12.3s"
 * Returns "—" for null/undefined.
 */
export function formatDuration(ms) {
  if (ms == null) return "—";
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const mins = Math.floor(ms / 60000);
  const secs = Math.floor((ms % 60000) / 1000);
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

// ── Scheduler + source-health normalizers (PR 13) ─────────────────────────────

export function normalizeSchedulerStatusFromApi(s) {
  return {
    // config INTENT as seen by the API process — NOT proof anything is ticking
    enabled: s.enabled ?? false,
    running: s.running ?? false,
    // durable runtime truth from the dedicated worker heartbeat (M7-4)
    workerRunning: s.worker_running ?? false,
    automaticIngestionActive: s.automatic_ingestion_active ?? s.worker_running ?? false,
    intervalMinutes: s.interval_minutes ?? 15,
    nextRunAt: s.next_run_at ?? null,
    lastStartedAt: s.last_started_at ?? null,
    lastFinishedAt: s.last_finished_at ?? null,
    lastStatus: s.last_status ?? "never_run",
    lastError: s.last_error ?? null,
    activeRun: s.active_run ?? null,
    lastResultSummary: s.last_result_summary ?? null,
  };
}

export function normalizeSourceHealthFromApi(h) {
  return {
    sourceId: h.source_id,
    displayName: h.display_name ?? h.source_id,
    enabled: h.enabled ?? false,
    sourceType: h.source_type ?? "rss",
    isPilot: h.is_pilot ?? false,
    freshness: h.freshness ?? "never_run",
    lastRunAt: h.last_run_at ?? null,
    lastStatus: h.last_status ?? null,
    lastFetchedCount: h.last_fetched_count ?? null,
    lastInsertedCount: h.last_inserted_count ?? null,
    lastFailedCount: h.last_failed_count ?? null,
    lastSkippedDuplicateCount: h.last_skipped_duplicate_count ?? null,
    consecutiveFailures: h.consecutive_failures ?? 0,
    lastErrorMessage: h.last_error_message ?? null,
  };
}

// Hebrew label + Tailwind classes per freshness value (source-health badge).
const FRESHNESS_BADGES = {
  healthy: {
    label: "תקין",
    colorClass: "bg-emerald-500/20 border-emerald-500/40 text-emerald-300",
  },
  stale: {
    label: "מיושן",
    colorClass: "bg-amber-500/20 border-amber-500/50 text-amber-300",
  },
  never_run: {
    label: "לא רץ עדיין",
    colorClass: "bg-gray-700/50 border-gray-600/50 text-gray-400",
  },
  disabled: {
    label: "כבוי",
    colorClass: "bg-gray-800/50 border-gray-700/50 text-gray-500",
  },
  error: {
    label: "שגיאה",
    colorClass: "bg-red-500/10 border-red-500/30 text-red-400",
  },
};

export function freshnessBadge(freshness) {
  return FRESHNESS_BADGES[freshness] ?? FRESHNESS_BADGES.never_run;
}

export function sourceTypeLabel(sourceType) {
  if (sourceType === "html_scrape") return "Scraping";
  return "RSS";
}

// ── Calibration headline normalizer ──────────────────────────────────────────

export function normalizeCalibrationHeadlineFromApi(h) {
  return {
    id: h.id,
    title: h.title,
    sport: h.sport,
    league: h.league ?? null,
    entities: h.entities ?? [],
    eventType: h.event_type,
    importance: h.importance,
    tags: h.tags ?? [],
  };
}

const DECISION_LABELS_HE = {
  hidden: "מוסתר",
  low_feed: "נמוך",
  feed: "רגיל",
  high_feed: "חשוב",
  push: "דורש תשומת לב",
};

/**
 * Format a ratio (0.0–1.0) as a percentage string: 0.5667 -> "56.7%"
 * Returns "—" for null/undefined.
 */
export function formatPercent(ratio) {
  if (ratio == null) return "—";
  return `${(ratio * 100).toFixed(1)}%`;
}

// ── M7-8 (#154): notification observability helpers (pure; node-tested) ──────

export const NOTIFICATION_STATUS_LABELS = {
  pending: { label: "ממתין", className: "text-signal-feed" },
  claimed: { label: "בשליחה (בדיקה ידנית אם נתקע)", className: "text-signal-push" },
  sent: { label: "נשלח", className: "text-signal-high" },
  failed_retryable: { label: "נכשל — ינוסה שוב", className: "text-signal-push" },
  failed_final: { label: "נכשל סופית", className: "text-signal-hidden" },
  unknown: { label: "לא ידוע — לא יישלח שוב", className: "text-signal-hidden" },
  suppressed_watermark: { label: "הודחק (לפני הפעלה)", className: "text-text-dim" },
};

// Events requiring a human decision: unknown outcomes (never auto-resent) and
// stuck claims (crash between claim and result).
export function manualReviewEvents(events) {
  return (events || []).filter(
    (e) => e.status === "unknown" || e.status === "claimed"
  );
}

// The health axis for the panel header: enabled without configuration is a
// misconfiguration state the operator must see.
export function notificationsStateLabel(health) {
  if (!health) return { label: "—", degraded: false };
  if (!health.enabled) return { label: "כבוי", degraded: false };
  if (!health.configured) return { label: "פעיל (חסרה תצורה)", degraded: true };
  if (health.unknown > 0 || health.consecutive_delivery_failures > 0) {
    return { label: "פעיל — דורש בדיקה", degraded: true };
  }
  return { label: "פעיל", degraded: false };
}
