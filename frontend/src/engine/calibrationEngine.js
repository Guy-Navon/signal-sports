/**
 * Calibration Inference Engine
 *
 * Given a set of user ratings on synthetic headlines, infer a draft preference profile.
 * All logic is pure and deterministic — no LLM, no backend, no external calls.
 *
 * Rating → decision mapping:
 *   push            → "push"      (I want to know immediately)
 *   interesting     → "high_feed" (I find this interesting)
 *   neutral         → "low_feed"  (I don't mind seeing it)
 *   not_interesting → "hidden"    (not for me)
 *   never_show      → "hidden"    (strong suppression)
 */

import { DECISION_RANK } from "./relevanceEngine";

// ── Constants ─────────────────────────────────────────────────────────────────

export const RATINGS = {
  push: "push",
  interesting: "interesting",
  neutral: "neutral",
  not_interesting: "not_interesting",
  never_show: "never_show"
};

export const RATING_LABELS_HE = {
  push: "תעדכן אותי מיד",
  interesting: "מעניין",
  neutral: "סבבה, לא קריטי",
  not_interesting: "לא מעניין",
  never_show: "אל תראה לי כאלה"
};

const POSITIVE_RATINGS = ["push", "interesting"];
const NEGATIVE_RATINGS = ["not_interesting", "never_show"];

// Event types considered major enough for titles_only/major detection
const MAJOR_EVENT_TYPES = [
  "grand_slam_winner", "grand_slam_final",
  "title_win", "finals_result",
  "star_trade", "major_trade"
];

const TOPIC_LABELS_HE = {
  "basketball::EuroLeague": "יורוליג",
  "basketball::Israeli Basketball League": "כדורסל ישראלי",
  "basketball::NBA": "NBA",
  "basketball::Spanish ACB": "כדורסל ספרד (ACB)",
  "basketball::Turkish BSL": "כדורסל טורקיה (BSL)",
  "basketball::Greek Basket League": "כדורסל יוון",
  "basketball::Italian LBA": "כדורסל איטליה (LBA)",
  "basketball::French LNB": "כדורסל צרפת (LNB)",
  "football::Israeli Premier League": "ליגת על (כדורגל)",
  "football::Ligue 1": "ליגה 1 צרפת (כדורגל)",
  "football::Bundesliga": "בונדסליגה",
  "football::general": "כדורגל",
  "tennis::Grand Slam": "גראנד סלאם",
  "tennis::Wimbledon": "וימבלדון",
  "tennis::general": "טניס"
};

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Infer a draft preference profile from calibration ratings.
 *
 * @param {Object} ratings      Map of { headlineId: ratingKey }
 * @param {Array}  headlines    Array of calibration headline objects
 * @returns {InferenceDraft}
 *
 * InferenceDraft shape:
 * {
 *   inferredTopics: Array<{
 *     topicKey, label, sport, league, priority, mode,
 *     entities, eventRules, reasoning
 *   }>,
 *   followedEntities: string[],
 *   mutedCandidates: string[],
 *   reasoning: string[]
 * }
 */
export function inferPreferenceDraftFromCalibration(ratings, headlines) {
  const ratedHeadlines = headlines
    .filter(h => ratings[h.id] !== undefined)
    .map(h => ({ ...h, rating: ratings[h.id] }));

  if (ratedHeadlines.length === 0) {
    return {
      inferredTopics: [],
      followedEntities: [],
      mutedCandidates: [],
      reasoning: ["אין כותרות מדורגות עדיין"]
    };
  }

  const topicGroups = {};    // "sport::league" → { sport, league, ratedItems[] }
  const entityVotes = {};    // entity → { positive: 0, negative: 0 }
  const globalReasoning = [];

  // ── Pass 1: group by topic, accumulate entity votes ───────────
  for (const item of ratedHeadlines) {
    const leagueKey = item.league || "general";
    const key = `${item.sport}::${leagueKey}`;

    if (!topicGroups[key]) {
      topicGroups[key] = { sport: item.sport, league: item.league, ratedItems: [] };
    }
    topicGroups[key].ratedItems.push({ headline: item, rating: item.rating });

    for (const entity of (item.entities || [])) {
      if (!entityVotes[entity]) entityVotes[entity] = { positive: 0, negative: 0 };
      if (POSITIVE_RATINGS.includes(item.rating)) entityVotes[entity].positive++;
      if (NEGATIVE_RATINGS.includes(item.rating)) entityVotes[entity].negative++;
    }
  }

  // ── Pass 2: build topics ──────────────────────────────────────
  const inferredTopics = [];
  const mutedCandidates = [];
  const mutedSports = new Set();

  for (const [topicKey, group] of Object.entries(topicGroups)) {
    const { sport, league, ratedItems } = group;
    const positiveItems = ratedItems.filter(r => POSITIVE_RATINGS.includes(r.rating));
    const negativeItems = ratedItems.filter(r => NEGATIVE_RATINGS.includes(r.rating));
    const neverShowItems = ratedItems.filter(r => r.rating === "never_show");

    // Build event rules: for each eventType take the highest-ranked decision
    const eventRules = {};
    for (const { headline, rating } of ratedItems) {
      const decision = ratingToDecision(rating);
      const existing = eventRules[headline.eventType];
      if (!existing || DECISION_RANK[decision] > DECISION_RANK[existing]) {
        eventRules[headline.eventType] = decision;
      }
    }

    // Collect entities that appeared in positively-rated articles for this topic
    const topicEntities = new Set();
    for (const { headline, rating } of ratedItems) {
      if (POSITIVE_RATINGS.includes(rating)) {
        for (const e of (headline.entities || [])) topicEntities.add(e);
      }
    }

    // Mute candidate: all-negative OR any "never_show"
    const allNegative = positiveItems.length === 0 && negativeItems.length > 0;
    if (allNegative && !mutedSports.has(sport)) {
      mutedCandidates.push(sport);
      mutedSports.add(sport);
      globalReasoning.push(
        `${topicLabel(sport, league)} — כל הכותרות דורגו שלילית → מועמד להשתקה`
      );
    }
    if (neverShowItems.length > 0 && !mutedSports.has(sport)) {
      mutedCandidates.push(sport);
      mutedSports.add(sport);
      globalReasoning.push(
        `${topicLabel(sport, league)} — דורג ״אל תראה לי כאלה״ → מועמד להשתקה`
      );
    }

    // Always create the topic entry (even muted — user should review the rules)
    const priority = inferPriority(positiveItems.length, ratedItems.length);
    const mode = inferMode(ratedItems);
    const topicReasoning = [
      `${positiveItems.length}/${ratedItems.length} כותרות דורגו בחיוב`
    ];
    if (mode !== "all") {
      topicReasoning.push(`מצב מזוהה: ${mode}`);
    }

    inferredTopics.push({
      topicKey,
      label: topicLabel(sport, league),
      sport,
      league,
      priority,
      mode,
      entities: [...topicEntities],
      eventRules,
      reasoning: topicReasoning
    });
  }

  // ── Pass 3: infer followed entities ──────────────────────────
  // Entities that appeared only in positive articles (never in negative ones)
  const followedEntities = Object.entries(entityVotes)
    .filter(([, v]) => v.positive > 0 && v.negative === 0)
    .map(([entity]) => entity);

  if (followedEntities.length > 0) {
    globalReasoning.push(`ישויות שזוהו כרלוונטיות: ${followedEntities.join(", ")}`);
  }

  return {
    inferredTopics,
    followedEntities,
    mutedCandidates,
    reasoning: globalReasoning
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Convert a user rating to a feed decision level.
 */
function ratingToDecision(rating) {
  const MAP = {
    push: "push",
    interesting: "high_feed",
    neutral: "low_feed",
    not_interesting: "hidden",
    never_show: "hidden"
  };
  return MAP[rating] ?? "hidden";
}

/**
 * Infer topic mode from rating patterns.
 *
 * - followed_entities_only: positives have exclusive entities not seen in negatives
 * - titles_only: only major-event articles rate positively, non-major rate negatively
 * - all: mixed or unclear pattern — show everything, rely on event rules to filter
 */
function inferMode(ratedItems) {
  const positiveRatings = ratedItems.filter(r => POSITIVE_RATINGS.includes(r.rating));
  const negativeRatings = ratedItems.filter(r => NEGATIVE_RATINGS.includes(r.rating));

  // Need both positive and negative samples to infer a restrictive mode
  if (positiveRatings.length === 0 || negativeRatings.length === 0) return "all";

  // followed_entities_only: positive articles mention entities that negative articles do not
  const positiveWithEntities = positiveRatings.filter(
    r => (r.headline.entities || []).length > 0
  );
  if (positiveWithEntities.length > 0) {
    const negativeEntitySet = new Set(
      negativeRatings.flatMap(r => r.headline.entities || [])
    );
    const exclusiveEntities = positiveWithEntities
      .flatMap(r => r.headline.entities || [])
      .filter(e => !negativeEntitySet.has(e));

    if (exclusiveEntities.length > 0) {
      return "followed_entities_only";
    }
  }

  // titles_only: every positive is a major event AND every negative is not a major event
  const allPositiveMajor = positiveRatings.every(r =>
    MAJOR_EVENT_TYPES.includes(r.headline.eventType)
  );
  const allNegativeNonMajor = negativeRatings.every(r =>
    !MAJOR_EVENT_TYPES.includes(r.headline.eventType)
  );
  if (allPositiveMajor && allNegativeNonMajor) return "titles_only";

  return "all";
}

/**
 * Infer topic priority (0–100) from the ratio of positive ratings.
 */
function inferPriority(positiveCount, total) {
  if (total === 0) return 30;
  const ratio = positiveCount / total;
  if (ratio >= 0.8) return 85;
  if (ratio >= 0.6) return 70;
  if (ratio >= 0.4) return 50;
  if (ratio >= 0.2) return 30;
  return 15;
}

/**
 * Get a Hebrew display label for a (sport, league) pair.
 */
function topicLabel(sport, league) {
  const key = `${sport}::${league || "general"}`;
  return TOPIC_LABELS_HE[key] ?? sport;
}
