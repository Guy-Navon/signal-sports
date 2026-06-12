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
    sourceDisplayName: a.source_display_name,
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
