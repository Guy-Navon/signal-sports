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
export function normalizeScoredArticleFromApi(sa) {
  const article = normalizeArticleFromApi(sa.article);
  return {
    ...article,
    type: "article",
    score: {
      decision: sa.decision,
      label: DECISION_LABELS_HE[sa.decision] ?? sa.decision,
      matchedTopic: sa.matched_topic ?? null,
      matchedRule: sa.matched_event_rule ?? null,
      reasoning: sa.reasoning ?? [],
    },
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
    enabled: s.enabled ?? false,
    running: s.running ?? false,
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
