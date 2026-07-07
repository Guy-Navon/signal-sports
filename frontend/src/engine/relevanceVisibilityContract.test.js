/**
 * Issue #29 — Relevance Visibility Contract (frontend mirror of
 * backend/tests/test_relevance_visibility_contract.py).
 *
 * Covers competition-aware league/league_group matching (explicit / legacy /
 * team-membership reach), the membership-only feed ceiling, the
 * entityIds-first identity contract (both for membership reach and for
 * entity backing), the explicit team/competition event-reach allowlists
 * (fail-closed for unlisted event types, `interview` deliberately excluded),
 * the removed major_importance_fallback leak, and the documented
 * sport=unknown behavior.
 *
 * Test-local article/profile fixtures are used throughout, mirroring the
 * backend file's approach — mockArticles.js stays untouched.
 */
import { describe, expect, it } from "vitest";
import { userProfiles } from "@/data/userProfiles";
import {
  scoreArticle,
  TEAM_ANCHORED_EVENTS,
  COMPETITION_ANCHORED_EVENTS
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
      eventRules: {
        match_result: "feed",
        signing: "feed",
        negotiation: "feed",
        interview: "feed",
        major_signing: "high_feed"
      }
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

describe("event-reach allowlists", () => {
  it("are disjoint", () => {
    for (const e of TEAM_ANCHORED_EVENTS) {
      expect(COMPETITION_ANCHORED_EVENTS.has(e)).toBe(false);
    }
  });

  it("exclude interview from both", () => {
    expect(TEAM_ANCHORED_EVENTS.has("interview")).toBe(false);
    expect(COMPETITION_ANCHORED_EVENTS.has("interview")).toBe(false);
  });
});

describe("league-visibility suite", () => {
  it("Maccabi Ramat Gan signing visible via IBL follow, not Maccabi-TLV-level", () => {
    const article = makeArticle({
      entities: ["Maccabi Ramat Gan"],
      entityIds: ["team:maccabi_ramat_gan"],
      eventType: "signing",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, guy);
    expect(["feed", "high_feed"]).toContain(result.decision);
    expect(result.matchedTopic).toBe("israeli_basketball");
    expect(result.matchedTopic).not.toBe("maccabi_tel_aviv_basketball");
  });

  it("Hapoel Tel Aviv Basketball roster release visible via broad league follow", () => {
    const article = makeArticle({
      entities: ["Hapoel Tel Aviv Basketball"],
      entityIds: ["team:hapoel_tlv_bb"],
      eventType: "release",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, guy);
    expect(result.decision).not.toBe("hidden");
    expect(["israeli_basketball", "euroleague"]).toContain(result.matchedTopic);
    expect(result.reasoning.some(line => line.includes("via_team_membership"))).toBe(true);
  });

  it("Israeli roster story without league keyword visible via team-membership reach", () => {
    const article = makeArticle({
      entities: ["Maccabi Kiryat Gat"],
      entityIds: ["team:maccabi_kiryat_gat"],
      eventType: "negotiation",
      taxonomyVersion: 1
    });
    expect(scoreArticle(article, guy).decision).not.toBe("hidden");
  });

  it("correctly-classified EuroLeague article is visible via explicit evidence", () => {
    const article = makeArticle({
      entities: ["Panathinaikos"],
      primaryCompetition: "comp:euroleague",
      eventType: "match_result",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, guy);
    expect(result.decision).not.toBe("hidden");
    expect(result.matchedTopic).toBe("euroleague");
  });
});

describe("team-anchored vs competition-anchored reach", () => {
  it("Maccabi domestic game (competition-anchored) not visible to EuroLeague-only follower", () => {
    const article = makeArticle({
      entities: ["Maccabi Tel Aviv Basketball"],
      entityIds: ["team:maccabi_tlv_bb"],
      primaryCompetition: "comp:ibl",
      eventType: "match_result",
      importance: "high",
      taxonomyVersion: 1
    });
    expect(scoreArticle(article, euroleagueOnlyProfile).decision).toBe("hidden");
  });

  it("Maccabi EuroLeague signing (team-anchored) reaches EuroLeague-only follower via membership", () => {
    const article = makeArticle({
      entities: ["Maccabi Tel Aviv Basketball"],
      entityIds: ["team:maccabi_tlv_bb"],
      eventType: "signing",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, euroleagueOnlyProfile);
    expect(result.decision).not.toBe("hidden");
    expect(result.reasoning.some(line => line.includes("via_team_membership: comp:euroleague"))).toBe(true);
  });

  it("interview does not reach EuroLeague-only follower via membership", () => {
    const article = makeArticle({
      entities: ["Maccabi Tel Aviv Basketball"],
      entityIds: ["team:maccabi_tlv_bb"],
      eventType: "interview",
      taxonomyVersion: 1
    });
    expect(scoreArticle(article, euroleagueOnlyProfile).decision).toBe("hidden");
  });

  it("unlisted event type gets no membership reach (fail-closed)", () => {
    const negotiation = makeArticle({
      entities: ["Maccabi Ramat Gan"],
      entityIds: ["team:maccabi_ramat_gan"],
      eventType: "negotiation",
      taxonomyVersion: 1
    });
    const rumor = makeArticle({
      entities: ["Maccabi Ramat Gan"],
      entityIds: ["team:maccabi_ramat_gan"],
      eventType: "rumor",
      taxonomyVersion: 1
    });
    expect(scoreArticle(negotiation, guy).decision).not.toBe("hidden");
    expect(scoreArticle(rumor, guy).decision).toBe("hidden");
  });

  it("release event reaches IBL follower via membership", () => {
    const article = makeArticle({
      entities: ["Hapoel Holon"],
      entityIds: ["team:hapoel_holon"],
      eventType: "release",
      taxonomyVersion: 1
    });
    expect(scoreArticle(article, guy).decision).not.toBe("hidden");
  });
});

describe("entityIds-first identity contract", () => {
  it("post-facts membership reach ignores a stale legacy entities field", () => {
    const article = makeArticle({
      entities: ["Maccabi Ramat Gan"], // present, resolvable — must be ignored
      entityIds: [],
      eventType: "negotiation",
      taxonomyVersion: 1
    });
    expect(scoreArticle(article, guy).decision).toBe("hidden");
  });

  it("post-facts entity backing survives an empty legacy entities field", () => {
    const article = makeArticle({
      entities: [],
      entityIds: ["player:deni_avdija"],
      eventType: "major_trade",
      taxonomyVersion: 1
    });
    expect(scoreArticle(article, guy).decision).toBe("push");
  });

  it("legacy pre-taxonomy row still works through the entities fallback", () => {
    const article = makeArticle({
      entities: ["Maccabi Ramat Gan"],
      entityIds: [],
      eventType: "negotiation",
      taxonomyVersion: null
    });
    expect(scoreArticle(article, guy).decision).not.toBe("hidden");
  });
});

describe("membership-only feed ceiling / push discipline", () => {
  it("caps at feed without entity backing even under importance boost", () => {
    const article = makeArticle({
      entities: ["Ironi Ramat Gan"],
      entityIds: ["team:ironi_ramat_gan"],
      eventType: "major_signing",
      importance: "very_high",
      taxonomyVersion: 1
    });
    expect(scoreArticle(article, guy).decision).toBe("feed");
  });

  it("Deni trade is still push despite matching via membership reach", () => {
    const article = makeArticle({
      entities: ["Deni Avdija"],
      entityIds: ["player:deni_avdija"],
      eventType: "major_trade",
      importance: "high",
      taxonomyVersion: 1
    });
    expect(scoreArticle(article, guy).decision).toBe("push");
  });
});

describe("no low_feed without a legitimate matched scope", () => {
  it("generic international noise is hidden, not low_feed", () => {
    const article = makeArticle({
      sport: "football",
      league: "Portuguese Liga",
      eventType: "regular_season_result",
      importance: "very_high",
      taxonomyVersion: null
    });
    expect(scoreArticle(article, guy).decision).toBe("hidden");
  });
});

describe("sport=unknown handling", () => {
  it("survives via explicit competition evidence", () => {
    const article = makeArticle({
      sport: "unknown",
      primaryCompetition: "comp:euroleague",
      eventType: "match_result",
      taxonomyVersion: 1
    });
    expect(scoreArticle(article, euroleagueOnlyProfile).decision).not.toBe("hidden");
  });

  it("cannot reach via membership (entities always cleared on abstention)", () => {
    const article = makeArticle({
      sport: "unknown",
      eventType: "signing",
      taxonomyVersion: 1
    });
    expect(scoreArticle(article, euroleagueOnlyProfile).decision).toBe("hidden");
  });
});

describe("explicit mute overrides membership reach", () => {
  it("mutes even a membership-matched article", () => {
    const mutedGuy = { ...guy, mutedTopics: ["basketball"] };
    const article = makeArticle({
      entities: ["Maccabi Ramat Gan"],
      entityIds: ["team:maccabi_ramat_gan"],
      eventType: "negotiation",
      importance: "very_high",
      taxonomyVersion: 1
    });
    const result = scoreArticle(article, mutedGuy);
    expect(result.decision).toBe("hidden");
    expect(result.matchedRule).toBe("muted_topic");
  });
});
