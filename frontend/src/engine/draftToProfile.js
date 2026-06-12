/**
 * Calibration Draft → User Profile conversion
 *
 * Converts an InferenceDraft produced by calibrationEngine into a UserProfile
 * that is fully compatible with the relevance engine.
 *
 * Design decisions:
 * - entityEventRules are generated for followed_entities_only topics where
 *   specific entities have high-priority event decisions (push or high_feed).
 *   This is consistent with the entityEventRules model introduced in PR 2.6.
 * - Legacy keys like "deni_avdija_trade" are never generated.
 * - Muting is conservative: only when the draft's mutedCandidates list is populated,
 *   which requires all-negative ratings OR at least one never_show in a topic.
 * - This function is pure: no side effects, no context, no UI imports.
 */

export const SANDBOX_PROFILE_ID = "calibrated_sandbox";
export const SANDBOX_DISPLAY_NAME = "הפרופיל המכויל שלי";

/**
 * Convert an InferenceDraft to a UserProfile.
 *
 * @param {InferenceDraft} draft - output of inferPreferenceDraftFromCalibration()
 * @returns {UserProfile} - compatible with scoreArticle()
 */
export function convertCalibrationDraftToUserProfile(draft) {
  const topics = draft.inferredTopics.map(inferred => {
    const leagues = buildLeaguesList(inferred.league);
    const topicId = topicKeyToId(inferred.topicKey);

    const { entityEventRules, eventRules } = buildEntityRules(
      inferred.eventRules,
      inferred.entities,
      inferred.mode
    );

    const topic = {
      topicId,
      label: inferred.label,
      sport: inferred.sport,
      scope: inferred.scope,  // preserve scope inferred by calibrationEngine
      priority: inferred.priority,
      mode: inferred.mode,
      leagues,
      entities: inferred.entities,
      eventRules
    };

    if (Object.keys(entityEventRules).length > 0) {
      topic.entityEventRules = entityEventRules;
    }

    return topic;
  });

  // Conservative muting: only mute a sport if NO other topic in the profile
  // has positive interest in that sport (priority > 15 means at least one positively-rated
  // article exists for that sport). This prevents a single all-negative NBA topic from
  // muting "basketball" globally and hiding EuroLeague or other basketball articles that
  // the user never rated negatively.
  const sportsWithPositiveInterest = new Set(
    draft.inferredTopics.filter(t => t.priority > 15).map(t => t.sport)
  );
  const mutedTopics = [...new Set(
    draft.mutedCandidates.filter(s => !sportsWithPositiveInterest.has(s))
  )];

  return {
    userId: SANDBOX_PROFILE_ID,
    displayName: SANDBOX_DISPLAY_NAME,
    language: "he",
    profileType: "calibration_generated",
    topics,
    mutedTopics,
    mutedSources: [],
    followedEntities: draft.followedEntities
  };
}

/**
 * Build entityEventRules for followed_entities_only topics.
 *
 * For topics in followed_entities_only mode with specific entities, place
 * high-priority rules (push, high_feed) in entityEventRules[entity] so the
 * engine can apply them explicitly per entity. Generic eventRules are kept
 * as fallbacks for lower-priority or edge-case events.
 *
 * For all-mode or entity-less topics: no entityEventRules are generated,
 * since the generic eventRules already handle the filtering.
 *
 * Never generates legacy keys like "deni_avdija_trade" or "deni_avdija_news".
 */
function buildEntityRules(eventRules, entities, mode) {
  if (entities.length === 0 || mode !== "followed_entities_only") {
    return { entityEventRules: {}, eventRules };
  }

  const HIGH_PRIORITY = ["push", "high_feed"];
  const entityEventRules = {};

  for (const entity of entities) {
    const entitySpecific = {};
    for (const [eventType, decision] of Object.entries(eventRules)) {
      if (HIGH_PRIORITY.includes(decision)) {
        entitySpecific[eventType] = decision;
      }
    }
    if (Object.keys(entitySpecific).length > 0) {
      entityEventRules[entity] = entitySpecific;
    }
  }

  // eventRules remain as fallbacks (for lower-priority events and edge cases)
  return { entityEventRules, eventRules };
}

function buildLeaguesList(league) {
  if (!league || league === "general") return [];
  return [league];
}

/**
 * Convert a topicKey ("basketball::NBA") to a stable topic ID slug.
 * Prefixed with "calibrated_" to distinguish from hardcoded topic IDs.
 */
function topicKeyToId(topicKey) {
  return "calibrated_" + topicKey
    .toLowerCase()
    .replace(/::/g, "_")
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_]/g, "");
}

/**
 * Preview what entityEventRules would be generated for a draft topic.
 * Used by the calibration UI to show what will happen on apply.
 * Returns null if no entity-specific rules would be generated.
 *
 * @param {{ mode, entities, eventRules }} topic - an inferredTopic from the draft
 * @returns {Object|null}
 */
export function previewEntityEventRules(topic) {
  const HIGH_PRIORITY = ["push", "high_feed"];
  if (
    topic.mode !== "followed_entities_only" ||
    topic.entities.length === 0
  ) {
    return null;
  }

  const result = {};
  for (const entity of topic.entities) {
    const rules = {};
    for (const [eventType, decision] of Object.entries(topic.eventRules)) {
      if (HIGH_PRIORITY.includes(decision)) {
        rules[eventType] = decision;
      }
    }
    if (Object.keys(rules).length > 0) {
      result[entity] = rules;
    }
  }

  return Object.keys(result).length > 0 ? result : null;
}
