/**
 * Relevance Scoring Engine v2
 *
 * Core logic: given an article and a user profile,
 * return a decision: hidden | low_feed | feed | high_feed | push
 * AND a full reasoning explanation for the debug panel.
 *
 * Push philosophy: push is RARE. It means "stop what you're doing and read this."
 * - Confirmed signing/official action
 * - Major entity-specific trade (e.g. Deni Avdija trade)
 * - Title win for a primary team
 * - Critical injury to a followed player
 * The importance boost NEVER elevates to push automatically — push must be explicitly
 * declared in eventRules or in topic.entityEventRules for a specific entity + event.
 */

export const DECISION_RANK = {
  hidden: 0,
  low_feed: 1,
  feed: 2,
  high_feed: 3,
  push: 4
};

export const DECISION_LABELS_HE = {
  hidden: "מוסתר",
  low_feed: "נמוך",
  feed: "רגיל",
  high_feed: "חשוב",
  push: "דורש תשומת לב"
};


/**
 * Main scoring function.
 * @param {object} article
 * @param {object} profile
 * @param {object} [options]
 * @param {Set<string>} [options.disabledSourceIds] - globally disabled source IDs (from Sources page)
 */
export function scoreArticle(article, profile, options = {}) {
  const { disabledSourceIds = new Set() } = options;
  const reasoning = [];
  let matchedTopic = null;
  let matchedRule = null;

  reasoning.push(`פרופיל: ${profile.displayName}`);

  // ── Step 1a: Globally disabled sources (Sources page toggle) ──
  if (disabledSourceIds.has(article.source)) {
    reasoning.push(`מקור כבוי (Sources page): ${article.source}`);
    return buildResult("hidden", reasoning, null, "disabled_source");
  }

  // ── Step 1b: Muted sources (user profile preference) ─────────
  if (profile.mutedSources?.includes(article.source)) {
    reasoning.push(`מקור מושתק: ${article.source}`);
    return buildResult("hidden", reasoning, null, "muted_source");
  }

  // ── Step 2: Muted topics ──────────────────────────────────────
  if (profile.mutedTopics?.length > 0) {
    const articleTopicIds = getArticleTopicIds(article);
    const muted = articleTopicIds.find(t => profile.mutedTopics.includes(t));
    if (muted) {
      reasoning.push(`נושא מושתק: ${muted}`);
      return buildResult("hidden", reasoning, null, "muted_topic");
    }
  }

  // ── Step 3: Find matching topics ─────────────────────────────
  const matchingTopics = findMatchingTopics(article, profile);

  if (matchingTopics.length === 0) {
    reasoning.push(`ספורט: ${article.sport}, ליגה: ${article.league || "—"}`);
    reasoning.push(`לא נמצאה התאמה לאף נושא בפרופיל`);
    reasoning.push(`החלטה סופית: מוסתר`);
    return buildResult("hidden", reasoning, null, "no_matching_topic");
  }

  // ── Step 4: Score against each matching topic, take best ─────
  let bestDecision = "hidden";
  let bestTopicId = null;
  let bestRule = null;
  let bestTopicReasoning = [];

  for (const topic of matchingTopics) {
    const { topicDecision, topicRule, topicReasoning } = scoreAgainstTopic(article, topic, profile);
    if (DECISION_RANK[topicDecision] > DECISION_RANK[bestDecision]) {
      bestDecision = topicDecision;
      bestTopicId = topic.topicId;
      bestRule = topicRule;
      bestTopicReasoning = topicReasoning;
    }
  }

  reasoning.push(...bestTopicReasoning);
  reasoning.push(`החלטה סופית: ${DECISION_LABELS_HE[bestDecision]}`);

  return buildResult(bestDecision, reasoning, bestTopicId, bestRule);
}

/**
 * Score an article against a single topic.
 */
function scoreAgainstTopic(article, topic, profile) {
  const r = []; // reasoning for this topic
  r.push(`נושא: "${topic.label}" (עדיפות: ${topic.priority}, מצב: ${topic.mode})`);

  // ── Mode: muted ───────────────────────────────────────────────
  if (topic.mode === "muted") {
    r.push(`נושא מושתק → מוסתר`);
    return result("hidden", "topic_muted", r);
  }

  // ── Mode: followed_entities_only ─────────────────────────────
  if (topic.mode === "followed_entities_only") {
    return scoreFollowedEntitiesOnly(article, topic, profile, r);
  }

  // ── Mode: titles_only ─────────────────────────────────────────
  if (topic.mode === "titles_only") {
    const eventDecision = getEventDecision(article.eventType, topic.eventRules);
    if (!eventDecision || eventDecision === "hidden") {
      r.push(`מצב titles_only — אירוע: ${article.eventType} → מוסתר`);
      return result("hidden", "titles_only_no_match", r);
    }
    r.push(`מצב titles_only — אירוע: ${article.eventType} → ${DECISION_LABELS_HE[eventDecision]}`);
    return result(eventDecision, `event:${article.eventType}`, r);
  }

  // ── Mode: high_importance_only ────────────────────────────────
  if (topic.mode === "high_importance_only") {
    const lowImportance = ["low", "very_low"];
    if (lowImportance.includes(article.importance)) {
      r.push(`מצב high_importance_only — חשיבות: ${article.importance} → מוסתר`);
      return result("hidden", "low_importance", r);
    }
    r.push(`מצב high_importance_only — חשיבות: ${article.importance} (עובר)`);
    // Fall through to event rule check below
    const eventDecision = getEventDecision(article.eventType, topic.eventRules);
    if (eventDecision && eventDecision !== "hidden") {
      r.push(`כלל אירוע: ${article.eventType} → ${DECISION_LABELS_HE[eventDecision]}`);
      // No boost in this mode — return as-is (no push escalation from boost)
      return result(eventDecision, `event:${article.eventType}`, r);
    }
    // Importance-based fallback (no event rule matched)
    const fallback = importanceFallback(article.importance, topic.priority, r);
    return result(fallback, "importance_fallback", r);
  }

  // ── Mode: major_only ─────────────────────────────────────────
  if (topic.mode === "major_only") {
    const majorImportance = ["high", "very_high"];
    const eventDecision = getEventDecision(article.eventType, topic.eventRules);

    if (!majorImportance.includes(article.importance) && (!eventDecision || eventDecision === "hidden")) {
      r.push(`מצב major_only — חשיבות: ${article.importance}, אירוע: ${article.eventType} → מוסתר`);
      return result("hidden", "major_only_no_match", r);
    }

    if (eventDecision && eventDecision !== "hidden") {
      r.push(`מצב major_only — כלל אירוע: ${article.eventType} → ${DECISION_LABELS_HE[eventDecision]}`);
      return result(eventDecision, `event:${article.eventType}`, r);
    }

    if (majorImportance.includes(article.importance)) {
      r.push(`מצב major_only — חשיבות גבוהה ללא כלל ספציפי → low_feed`);
      return result("low_feed", "major_importance_fallback", r);
    }

    return result("hidden", "major_only_no_match", r);
  }

  // ── Mode: all (default) ───────────────────────────────────────
  return scoreAllMode(article, topic, profile, r);
}

/**
 * Score in "followed_entities_only" mode.
 * Entity match is REQUIRED. Then apply event-specific rules.
 * Push is only possible if explicitly declared for the entity-specific event.
 */
function scoreFollowedEntitiesOnly(article, topic, profile, r) {
  const articleEntities = article.entities || [];
  const relevantEntities = [
    ...new Set([...(topic.entities || []), ...(profile.followedEntities || [])])
  ];

  const entityMatch = articleEntities.find(e => relevantEntities.includes(e));

  if (!entityMatch) {
    r.push(`מצב followed_entities_only`);
    r.push(`ישויות במאמר: ${articleEntities.join(", ") || "אין"}`);
    r.push(`ישויות מעקב: ${relevantEntities.join(", ")}`);
    r.push(`לא נמצאה ישות תואמת → מוסתר`);
    return result("hidden", "entity_not_followed", r);
  }

  r.push(`ישות תואמת: ${entityMatch}`);

  // Entity-specific event rule (entityEventRules takes precedence over generic eventRules)
  const entityEventRule = getEventDecision(article.eventType, topic.entityEventRules?.[entityMatch]);
  if (entityEventRule !== null) {
    r.push(`כלל ספציפי לישות (${entityMatch}): ${article.eventType} → ${DECISION_LABELS_HE[entityEventRule]}`);
    if (entityEventRule === "hidden") return result("hidden", `entity_event:${article.eventType}`, r);
    const boosted = applyImportanceBoost(entityEventRule, article.importance, r);
    return result(boosted, `entity_event:${article.eventType}`, r);
  }

  // Check generic event rule
  const eventDecision = getEventDecision(article.eventType, topic.eventRules);

  if (eventDecision && eventDecision !== "hidden") {
    r.push(`כלל אירוע: ${article.eventType} → ${DECISION_LABELS_HE[eventDecision]}`);
    return result(eventDecision, `event:${article.eventType}`, r);
  }

  // Entity news catch-all
  const catchAll = topic.eventRules?.followed_entity_news;
  if (catchAll && catchAll !== "hidden") {
    r.push(`ישות תואמת (${entityMatch}) + catch-all → ${DECISION_LABELS_HE[catchAll]}`);
    return result(catchAll, "entity_news_catchall", r);
  }

  // Entity matched but no rule → feed (entity is relevant to user)
  r.push(`ישות תואמת (${entityMatch}), אין כלל ספציפי → feed`);
  return result("feed", "entity_match_default", r);
}

/**
 * Score in "all" mode (default).
 * Check entity match for boost context, then apply event rules + importance boost.
 * IMPORTANT: importance boost is capped at high_feed — never auto-escalates to push.
 *
 * Entity-specific event overrides: if an entity matches and topic.entityEventRules
 * has a rule for that entity + event type, it takes precedence over the generic
 * eventRules. This allows "major_trade → high_feed in general, but
 * entityEventRules["Deni Avdija"].major_trade → push."
 */
function scoreAllMode(article, topic, profile, r) {
  const articleEntities = article.entities || [];
  const topicEntities = topic.entities || [];
  const profileEntities = profile.followedEntities || [];
  const entityMatch = articleEntities.find(e =>
    topicEntities.includes(e) || profileEntities.includes(e)
  );

  if (entityMatch) {
    r.push(`ישות תואמת: ${entityMatch}`);
  }

  // Entity-specific event rule override (entityEventRules takes precedence over generic eventRules)
  if (entityMatch) {
    const entityEventRule = getEventDecision(article.eventType, topic.entityEventRules?.[entityMatch]);
    if (entityEventRule !== null) {
      r.push(`כלל ספציפי לישות (${entityMatch}): ${article.eventType} → ${DECISION_LABELS_HE[entityEventRule]}`);
      if (entityEventRule === "hidden") return result("hidden", `entity_event:${article.eventType}`, r);
      const boosted = applyImportanceBoost(entityEventRule, article.importance, r);
      return result(boosted, `entity_event:${article.eventType}`, r);
    }
  }

  // Check event-specific rule
  const eventDecision = getEventDecision(article.eventType, topic.eventRules);

  if (eventDecision !== null) {
    if (eventDecision === "hidden") {
      r.push(`כלל אירוע: ${article.eventType} → מוסתר`);
      return result("hidden", `event:${article.eventType}`, r);
    }

    r.push(`כלל אירוע: ${article.eventType} → ${DECISION_LABELS_HE[eventDecision]}`);

    // Apply entity boost: if entity matched AND event is only feed, bump to high_feed
    // But only if entity is explicitly in topic.entities (primary entities), not just followedEntities
    if (entityMatch && topicEntities.includes(entityMatch)) {
      const boosted = applyEntityBoost(eventDecision, r);
      if (boosted !== eventDecision) {
        return result(boosted, `event:${article.eventType}+entity_boost`, r);
      }
    }

    // Apply importance boost — CAPPED AT high_feed, never reaches push automatically
    const boosted = applyImportanceBoost(eventDecision, article.importance, r);
    return result(boosted, `event:${article.eventType}`, r);
  }

  // No event rule → fallback by importance + topic priority
  r.push(`אין כלל עבור אירוע: ${article.eventType}`);
  const fallback = importanceFallback(article.importance, topic.priority, r);
  return result(fallback, "importance_fallback", r);
}

/**
 * Get decision from eventRules, with alias resolution.
 * Returns null if no rule found (not "hidden").
 */
function getEventDecision(eventType, eventRules) {
  if (!eventRules) return null;
  if (eventRules[eventType] !== undefined) return eventRules[eventType];

  // Canonical aliases
  const aliases = {
    regular_season_result: ["match_result"],
    match_result: ["regular_season_result"],
    major_signing: ["signing"],
    signing: ["major_signing"],
    major_trade: ["star_trade"],
    star_trade: ["major_trade"],
    major_transfer: ["major_signing", "major_trade"],
    match_summary: ["match_result", "regular_season_result"]
  };

  for (const alias of (aliases[eventType] || [])) {
    if (eventRules[alias] !== undefined) return eventRules[alias];
  }

  return null;
}

/**
 * Entity boost: if entity match on a primary entity and decision is only feed → bump to high_feed.
 * Never exceeds high_feed (push must be explicit in eventRules).
 */
function applyEntityBoost(decision, reasoning) {
  if (decision === "feed") {
    reasoning.push(`ישות ראשית תואמת → שדרוג: feed → high_feed`);
    return "high_feed";
  }
  return decision;
}

/**
 * Importance boost: can upgrade one level BUT HARD CAP at high_feed.
 * Push is NEVER reached via automatic boost.
 */
function applyImportanceBoost(decision, importance, reasoning) {
  const ranks = ["hidden", "low_feed", "feed", "high_feed", "push"];
  const PUSH_RANK = 4;
  const HIGH_FEED_RANK = 3;

  if (importance === "very_high" && DECISION_RANK[decision] > 0) {
    const currentRank = DECISION_RANK[decision];
    // Hard cap: never auto-boost to push
    const targetRank = Math.min(currentRank + 1, HIGH_FEED_RANK);
    if (targetRank > currentRank) {
      const boosted = ranks[targetRank];
      reasoning.push(`חשיבות מאוד גבוהה → שדרוג: ${DECISION_LABELS_HE[decision]} → ${DECISION_LABELS_HE[boosted]} (push דורש הגדרה מפורשת)`);
      return boosted;
    }
  }
  return decision;
}

/**
 * Fallback when no event rule: decide by importance + topic priority.
 * Never reaches push via fallback.
 * very_low → always hidden (noise prevention).
 * low + low-priority topic → hidden; low + high-priority topic → low_feed.
 */
function importanceFallback(importance, topicPriority, reasoning) {
  let decision;
  if (importance === "very_high" && topicPriority >= 80) decision = "high_feed";
  else if (importance === "high" && topicPriority >= 80) decision = "feed";
  else if (importance === "medium" && topicPriority >= 70) decision = "feed";
  else if (importance === "high") decision = "feed";
  else if (importance === "medium") decision = "low_feed";
  else if (importance === "low" && topicPriority >= 70) decision = "low_feed";
  else decision = "hidden"; // very_low, or low with low-priority topic

  reasoning.push(`גיבוי לפי חשיבות (${importance}) + עדיפות (${topicPriority}) → ${DECISION_LABELS_HE[decision]}`);
  return decision;
}

/**
 * Find all topics in profile that match this article (by sport, league, or entity).
 */
function findMatchingTopics(article, profile) {
  const matched = [];

  for (const topic of profile.topics) {
    let matches = false;

    if (topic.sport && article.sport === topic.sport) matches = true;

    if (topic.leagues?.length > 0 && article.league) {
      if (topic.leagues.includes(article.league)) matches = true;
    }

    if (topic.entities?.length > 0 && article.entities?.length > 0) {
      if (article.entities.find(e => topic.entities.includes(e))) matches = true;
    }

    if (matches) matched.push(topic);
  }

  // Sort by priority descending (highest priority topic evaluated first)
  return matched.sort((a, b) => b.priority - a.priority);
}

function getArticleTopicIds(article) {
  const ids = [];
  if (article.sport) ids.push(article.sport);
  if (article.league) ids.push(article.league);
  return ids;
}

function buildResult(decision, reasoning, matchedTopic, matchedRule) {
  return { decision, label: DECISION_LABELS_HE[decision], reasoning, matchedTopic, matchedRule };
}

// Helper alias
function result(decision, rule, reasoning) {
  return { topicDecision: decision, topicRule: rule, topicReasoning: reasoning };
}

/**
 * Score all articles against a profile.
 */
export function scoreAllArticles(articles, profile, options = {}) {
  return articles.map(article => ({
    ...article,
    score: scoreArticle(article, profile, options)
  }));
}

/**
 * Score a cluster: best decision among its articles.
 */
export function scoreCluster(cluster, articles, profile, options = {}) {
  const clusterArticles = articles.filter(a => cluster.articleIds.includes(a.id));

  let bestDecision = "hidden";
  let bestReasoning = [];
  let bestMatchedTopic = null;
  let bestMatchedRule = null;

  for (const article of clusterArticles) {
    const s = scoreArticle(article, profile, options);
    if (DECISION_RANK[s.decision] > DECISION_RANK[bestDecision]) {
      bestDecision = s.decision;
      bestReasoning = s.reasoning;
      bestMatchedTopic = s.matchedTopic;
      bestMatchedRule = s.matchedRule;
    }
  }

  return {
    ...cluster,
    score: {
      decision: bestDecision,
      label: DECISION_LABELS_HE[bestDecision],
      reasoning: bestReasoning,
      matchedTopic: bestMatchedTopic,
      matchedRule: bestMatchedRule
    }
  };
}