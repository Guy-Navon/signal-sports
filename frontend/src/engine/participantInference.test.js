/**
 * Issue #40 Part B — participant-set competition inference (frontend mirror
 * of backend/tests/test_participant_inference.py).
 *
 * The required regression list from issue #40 must pass identically in both
 * engines: unique-intersection acceptance (NBA, EuroLeague), ambiguous/empty
 * abstention, team-entities-only participant selection, explicit-evidence
 * priority, no-push-by-itself, friendly_match exclusion, and the ceiling
 * exemption for participant-inferred matches.
 */
import { describe, expect, it } from "vitest";
import { userProfiles } from "@/data/userProfiles";
import {
  scoreArticle,
  COMPETITION_ANCHORED_EVENTS,
  PARTICIPANT_INFERENCE_EXCLUDED_EVENTS
} from "@/engine/relevanceEngine";

const guy = userProfiles.guy;

const euroleagueOnlyProfile = {
  userId: "test_euroleague_only",
  displayName: "Test EuroLeague-only",
  topics: [
    {
      topicId: "euroleague_only",
      label: "EuroLeague only",
      sport: "basketball",
      scope: "league",
      priority: 90,
      mode: "all",
      leagues: ["EuroLeague"],
      entities: [],
      eventRules: { match_result: "feed", playoff_result: "high_feed" }
    }
  ],
  mutedTopics: [],
  mutedSources: [],
  followedEntities: []
};

const nbaOnlyProfile = {
  userId: "test_nba_only",
  displayName: "Test NBA-only",
  topics: [
    {
      topicId: "nba_only",
      label: "NBA only",
      sport: "basketball",
      scope: "league",
      priority: 90,
      mode: "all",
      leagues: ["NBA"],
      entities: [],
      eventRules: { match_result: "feed", finals_result: "high_feed" }
    }
  ],
  mutedTopics: [],
  mutedSources: [],
  followedEntities: []
};

function makeArticle(overrides = {}) {
  return {
    id: "test_article",
    source: "test",
    sourceDisplayName: "Test",
    url: "https://example.com",
    title: "Test article",
    language: "he",
    publishedAt: "2026-06-12T00:00:00Z",
    sport: "basketball",
    league: null,
    entities: [],
    eventType: "match_result",
    importance: "medium",
    confidence: 0.9,
    tags: [],
    primaryCompetition: null,
    articleCompetitions: [],
    entityIds: [],
    taxonomyVersion: null,
    ...overrides
  };
}

/** Lakers vs Celtics game result, post-ArticleFacts row, NO explicit
 * competition evidence — the exact shape of the #29 QA hidden row. */
function nbaGame(overrides = {}) {
  return makeArticle({
    entities: ["Los Angeles Lakers", "Boston Celtics"],
    entityIds: ["team:la_lakers", "team:boston_celtics"],
    eventType: "match_result",
    importance: "medium",
    taxonomyVersion: 1,
    league: "NBA", // classifier/LLM string — deliberately NOT explicit evidence
    ...overrides
  });
}

const hasTrace = (result, needle) =>
  result.reasoning.some(r => r.includes(needle));

describe("participant inference — required regressions (issue #40)", () => {
  it("broad NBA follower sees a participant-inferred NBA game result", () => {
    const result = scoreArticle(nbaGame(), nbaOnlyProfile);
    expect(result.decision).toBe("feed");
    expect(hasTrace(result, "via_participant_inference: comp:nba")).toBe(true);
  });

  it("Guy sees the participant-inferred NBA game via his nba topic", () => {
    const result = scoreArticle(nbaGame(), guy);
    expect(result.decision).toBe("feed");
    expect(result.matchedTopic).toBe("nba");
  });

  it("EuroLeague-only follower sees Maccabi vs Real Madrid (unique {EuroLeague})", () => {
    const article = makeArticle({
      entityIds: ["team:maccabi_tlv_bb", "team:real_madrid_bb"],
      eventType: "match_result",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, euroleagueOnlyProfile);
    expect(result.decision).toBe("feed");
    expect(hasTrace(result, "via_participant_inference: comp:euroleague")).toBe(true);
  });

  it("EuroLeague-only follower does NOT see the ambiguous Israeli derby", () => {
    const article = makeArticle({
      entityIds: ["team:maccabi_tlv_bb", "team:hapoel_tlv_bb"],
      eventType: "match_result",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, euroleagueOnlyProfile);
    expect(result.decision).toBe("hidden");
  });

  it("explicit competition evidence outranks participant inference", () => {
    const article = makeArticle({
      entityIds: ["team:maccabi_tlv_bb", "team:hapoel_tlv_bb"],
      primaryCompetition: "comp:euroleague",
      eventType: "match_result",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, euroleagueOnlyProfile);
    expect(result.decision).toBe("feed");
    expect(hasTrace(result, "תחרות מפורשת")).toBe(true);
    expect(hasTrace(result, "via_participant_inference")).toBe(false);
  });

  it("participant inference never creates push by itself", () => {
    const article = nbaGame({ eventType: "finals_result", importance: "very_high" });
    const result = scoreArticle(article, nbaOnlyProfile);
    expect(result.decision).not.toBe("push");
  });

  it("empty intersection abstains (Lakers + Maccabi)", () => {
    const article = makeArticle({
      entityIds: ["team:la_lakers", "team:maccabi_tlv_bb"],
      eventType: "match_result",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, nbaOnlyProfile);
    expect(result.decision).toBe("hidden");
  });

  it("a single resolved team abstains", () => {
    const article = makeArticle({
      entityIds: ["team:la_lakers"],
      eventType: "match_result",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, nbaOnlyProfile);
    expect(result.decision).toBe("hidden");
  });

  it("players/coaches never act as participants (Lakers + LeBron = one team)", () => {
    const article = makeArticle({
      entityIds: ["team:la_lakers", "player:lebron_james"],
      eventType: "match_result",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, nbaOnlyProfile);
    expect(result.decision).toBe("hidden");
  });

  it("an incidental third team can only force abstention, never redirect", () => {
    const article = makeArticle({
      entityIds: ["team:la_lakers", "team:boston_celtics", "team:maccabi_tlv_bb"],
      eventType: "match_result",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, nbaOnlyProfile);
    expect(result.decision).toBe("hidden");
  });

  it("a third same-competition team keeps the unique inference", () => {
    const article = makeArticle({
      entityIds: ["team:la_lakers", "team:boston_celtics", "team:brooklyn_nets"],
      eventType: "match_result",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, nbaOnlyProfile);
    expect(result.decision).toBe("feed");
  });

  it("legacy rows infer via display strings", () => {
    const article = makeArticle({
      entities: ["Brooklyn Nets", "Sacramento Kings"],
      entityIds: [],
      taxonomyVersion: null,
      eventType: "match_result"
    });
    const result = scoreArticle(article, nbaOnlyProfile);
    expect(result.decision).toBe("feed");
    expect(hasTrace(result, "via_participant_inference: comp:nba")).toBe(true);
  });
});

describe("participant inference — boundaries", () => {
  it("friendly_match is excluded (a Maccabi–Real friendly is not a EuroLeague game)", () => {
    expect(PARTICIPANT_INFERENCE_EXCLUDED_EVENTS.has("friendly_match")).toBe(true);
    for (const e of PARTICIPANT_INFERENCE_EXCLUDED_EVENTS) {
      expect(COMPETITION_ANCHORED_EVENTS.has(e)).toBe(true);
    }
    const article = makeArticle({
      entityIds: ["team:maccabi_tlv_bb", "team:real_madrid_bb"],
      eventType: "friendly_match",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, euroleagueOnlyProfile);
    expect(result.decision).toBe("hidden");
  });

  it("team-anchored events keep using ordinary membership reach", () => {
    const article = makeArticle({
      entityIds: ["team:maccabi_tlv_bb", "team:real_madrid_bb"],
      eventType: "signing",
      taxonomyVersion: 1
    });
    const euroProfile = {
      ...euroleagueOnlyProfile,
      topics: [
        {
          ...euroleagueOnlyProfile.topics[0],
          eventRules: { match_result: "feed", signing: "feed" }
        }
      ]
    };
    const result = scoreArticle(article, euroProfile);
    expect(result.decision).toBe("feed");
    expect(hasTrace(result, "via_team_membership")).toBe(true);
    expect(hasTrace(result, "via_participant_inference")).toBe(false);
  });

  it("unlisted event types (interview) still get no inference", () => {
    const article = makeArticle({
      entityIds: ["team:maccabi_tlv_bb", "team:real_madrid_bb"],
      eventType: "interview",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, euroleagueOnlyProfile);
    expect(result.decision).toBe("hidden");
  });

  it("participant-inferred matches are NOT capped by the membership feed ceiling", () => {
    const article = makeArticle({
      entityIds: ["team:maccabi_tlv_bb", "team:real_madrid_bb"],
      eventType: "playoff_result",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, euroleagueOnlyProfile);
    expect(result.decision).toBe("high_feed");
    expect(hasTrace(result, "via_participant_inference")).toBe(true);
  });
});
