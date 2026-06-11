import { describe, it, expect } from "vitest";
import {
  convertCalibrationDraftToUserProfile,
  previewEntityEventRules,
  SANDBOX_PROFILE_ID,
  SANDBOX_DISPLAY_NAME
} from "./draftToProfile";
import { inferPreferenceDraftFromCalibration } from "./calibrationEngine";
import { calibrationHeadlines } from "../data/calibrationHeadlines";
import { scoreArticle } from "./relevanceEngine";
import { mockArticles } from "../data/mockArticles";

// ── Helpers ───────────────────────────────────────────────────────────────────

function findHeadline(id) {
  const h = calibrationHeadlines.find(h => h.id === id);
  if (!h) throw new Error(`Calibration headline ${id} not found`);
  return h;
}

function makeDraft(ratingMap) {
  return inferPreferenceDraftFromCalibration(ratingMap, calibrationHeadlines);
}

function makeProfile(ratingMap) {
  return convertCalibrationDraftToUserProfile(makeDraft(ratingMap));
}

// Rate Deni articles positively, Hornets/Wizards negatively → followed_entities_only NBA
const DENI_FAN_RATINGS = {
  cal_012: "push",        // Deni trade, NBA, major_trade
  cal_013: "interesting", // Deni injury, NBA, injury
  cal_011: "not_interesting" // Hornets/Wizards, NBA, regular_season_result — no Deni
};

// Rate all EuroLeague articles positively → all mode (no exclusive entity pattern)
const EUROLEAGUE_RATINGS = {
  cal_007: "interesting", // Real Madrid signing
  cal_008: "interesting", // Fenerbahce vs CSKA
  cal_009: "push"         // Final Four finals
};

// Rate football articles negatively → football muted
const FOOTBALL_MUTED_RATINGS = {
  cal_025: "never_show",  // Israeli league result
  cal_026: "not_interesting" // CL schedule
};

// ─────────────────────────────────────────────────────────────────────────────
// Profile structure
// ─────────────────────────────────────────────────────────────────────────────

describe("convertCalibrationDraftToUserProfile — profile structure", () => {
  it("sets userId to SANDBOX_PROFILE_ID", () => {
    const profile = makeProfile(DENI_FAN_RATINGS);
    expect(profile.userId).toBe(SANDBOX_PROFILE_ID);
    expect(profile.userId).toBe("calibrated_sandbox");
  });

  it("sets profileType to calibration_generated", () => {
    const profile = makeProfile(DENI_FAN_RATINGS);
    expect(profile.profileType).toBe("calibration_generated");
  });

  it("sets displayName to Hebrew sandbox label", () => {
    const profile = makeProfile(DENI_FAN_RATINGS);
    expect(profile.displayName).toBe(SANDBOX_DISPLAY_NAME);
  });

  it("empty draft produces a valid profile with no topics", () => {
    const profile = makeProfile({});
    expect(profile.userId).toBe(SANDBOX_PROFILE_ID);
    expect(profile.topics).toEqual([]);
    expect(profile.mutedTopics).toEqual([]);
    expect(profile.followedEntities).toEqual([]);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Topic ID generation
// ─────────────────────────────────────────────────────────────────────────────

describe("convertCalibrationDraftToUserProfile — topic ID generation", () => {
  it("generates calibrated_ prefixed topic ID from topicKey", () => {
    const profile = makeProfile(DENI_FAN_RATINGS);
    const nba = profile.topics.find(t => t.topicId.includes("nba"));
    expect(nba).toBeDefined();
    expect(nba.topicId).toBe("calibrated_basketball_nba");
  });

  it("league-less topics get valid IDs", () => {
    // cal_023 has league: null → "tennis::general" → "calibrated_tennis_general"
    const profile = makeProfile({ cal_023: "interesting" });
    const tennis = profile.topics.find(t => t.topicId.includes("tennis"));
    expect(tennis).toBeDefined();
    expect(tennis.topicId).toBe("calibrated_tennis_general");
    expect(tennis.leagues).toEqual([]);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// entityEventRules generation
// ─────────────────────────────────────────────────────────────────────────────

describe("convertCalibrationDraftToUserProfile — entityEventRules", () => {
  it("followed_entities_only topic generates entityEventRules for Deni Avdija", () => {
    const profile = makeProfile(DENI_FAN_RATINGS);
    const nba = profile.topics.find(t => t.topicId === "calibrated_basketball_nba");
    expect(nba).toBeDefined();
    expect(nba.mode).toBe("followed_entities_only");
    expect(nba.entityEventRules?.["Deni Avdija"]).toBeDefined();
  });

  it("entityEventRules only contains push and high_feed decisions", () => {
    const profile = makeProfile(DENI_FAN_RATINGS);
    const nba = profile.topics.find(t => t.topicId === "calibrated_basketball_nba");
    const deniRules = nba?.entityEventRules?.["Deni Avdija"] ?? {};
    const values = Object.values(deniRules);
    expect(values.length).toBeGreaterThan(0);
    for (const v of values) {
      expect(["push", "high_feed"]).toContain(v);
    }
  });

  it("Deni trade (push rating) produces push in entityEventRules", () => {
    const profile = makeProfile(DENI_FAN_RATINGS);
    const nba = profile.topics.find(t => t.topicId === "calibrated_basketball_nba");
    expect(nba.entityEventRules?.["Deni Avdija"]?.major_trade).toBe("push");
  });

  it("Deni injury (interesting rating) produces high_feed in entityEventRules", () => {
    const profile = makeProfile(DENI_FAN_RATINGS);
    const nba = profile.topics.find(t => t.topicId === "calibrated_basketball_nba");
    expect(nba.entityEventRules?.["Deni Avdija"]?.injury).toBe("high_feed");
  });

  it("all-mode topic does NOT generate entityEventRules", () => {
    const profile = makeProfile(EUROLEAGUE_RATINGS);
    const el = profile.topics.find(t => t.topicId === "calibrated_basketball_euroleague");
    expect(el).toBeDefined();
    expect(el.mode).toBe("all");
    expect(el.entityEventRules).toBeUndefined();
  });

  it("eventRules are retained as fallbacks on followed_entities_only topics", () => {
    const profile = makeProfile(DENI_FAN_RATINGS);
    const nba = profile.topics.find(t => t.topicId === "calibrated_basketball_nba");
    // eventRules still contains ALL inferred rules (including hidden for non-Deni)
    expect(nba.eventRules).toBeDefined();
    expect(Object.keys(nba.eventRules).length).toBeGreaterThan(0);
    // regular_season_result was rated not_interesting → hidden in eventRules
    expect(nba.eventRules.regular_season_result).toBe("hidden");
  });

  it("no legacy keys like deni_avdija_trade are generated", () => {
    const profile = makeProfile(DENI_FAN_RATINGS);
    const nba = profile.topics.find(t => t.topicId === "calibrated_basketball_nba");
    expect(nba.eventRules?.deni_avdija_trade).toBeUndefined();
    expect(nba.eventRules?.deni_avdija_news).toBeUndefined();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Muting and followedEntities
// ─────────────────────────────────────────────────────────────────────────────

describe("convertCalibrationDraftToUserProfile — muting and entities", () => {
  it("never_show rating triggers conservative muting via mutedTopics", () => {
    const profile = makeProfile(FOOTBALL_MUTED_RATINGS);
    expect(profile.mutedTopics).toContain("football");
  });

  it("mutedTopics has no duplicates", () => {
    const profile = makeProfile(FOOTBALL_MUTED_RATINGS);
    const unique = new Set(profile.mutedTopics);
    expect(unique.size).toBe(profile.mutedTopics.length);
  });

  it("followedEntities passed through from draft", () => {
    // Deni appears only in positive-rated articles → inferred as followedEntity
    const profile = makeProfile(DENI_FAN_RATINGS);
    expect(profile.followedEntities).toContain("Deni Avdija");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// previewEntityEventRules
// ─────────────────────────────────────────────────────────────────────────────

describe("previewEntityEventRules", () => {
  it("returns null for all-mode topic", () => {
    const topic = {
      mode: "all",
      entities: ["Real Madrid Basketball"],
      eventRules: { major_signing: "high_feed", match_result: "feed" }
    };
    expect(previewEntityEventRules(topic)).toBeNull();
  });

  it("returns null when no entities", () => {
    const topic = {
      mode: "followed_entities_only",
      entities: [],
      eventRules: { major_trade: "push" }
    };
    expect(previewEntityEventRules(topic)).toBeNull();
  });

  it("returns entity→rules map for followed_entities_only with push/high_feed", () => {
    const topic = {
      mode: "followed_entities_only",
      entities: ["Deni Avdija"],
      eventRules: { major_trade: "push", injury: "high_feed", regular_season_result: "hidden" }
    };
    const result = previewEntityEventRules(topic);
    expect(result).not.toBeNull();
    expect(result["Deni Avdija"]).toEqual({ major_trade: "push", injury: "high_feed" });
  });

  it("returns null when all eventRules are below high_feed", () => {
    const topic = {
      mode: "followed_entities_only",
      entities: ["Some Entity"],
      eventRules: { generic_news: "low_feed", schedule: "hidden" }
    };
    expect(previewEntityEventRules(topic)).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// PR 3.1 — sandbox feed visibility (end-to-end with mockArticles)
// ─────────────────────────────────────────────────────────────────────────────

// Realistic 6-headline scenario from PR 3.1 spec
const REALISTIC_RATINGS = {
  cal_001: "push",            // Maccabi negotiation, EuroLeague
  cal_002: "interesting",     // Maccabi signing, Israeli Basketball League
  cal_012: "push",            // Deni trade, NBA
  cal_011: "not_interesting", // Hornets/Wizards, NBA
  cal_022: "not_interesting", // Alcaraz early round, tennis
  cal_021: "interesting"      // Grand Slam winner, tennis
};

function scoreMockArticles(profile) {
  return mockArticles.map(a => ({ id: a.id, title: a.title, sport: a.sport, league: a.league, decision: scoreArticle(a, profile).decision }));
}

function getArticle(id) {
  const a = mockArticles.find(a => a.id === id);
  if (!a) throw new Error(`Article ${id} not found`);
  return a;
}

describe("PR 3.1 — sandbox feed visibility", () => {
  it("realistic 6-rating calibration produces a non-empty feed", () => {
    const draft = inferPreferenceDraftFromCalibration(REALISTIC_RATINGS, calibrationHeadlines);
    const profile = convertCalibrationDraftToUserProfile(draft);
    const scored = scoreMockArticles(profile);
    const visible = scored.filter(s => s.decision !== "hidden");
    expect(visible.length).toBeGreaterThan(0);
  });

  it("Maccabi negotiation and signing articles are visible in realistic scenario", () => {
    const draft = inferPreferenceDraftFromCalibration(REALISTIC_RATINGS, calibrationHeadlines);
    const profile = convertCalibrationDraftToUserProfile(draft);
    // article_037 is standalone Maccabi negotiation (EuroLeague)
    // article_056 is standalone Maccabi signing
    const neg = scoreArticle(getArticle("article_037"), profile);
    const sig = scoreArticle(getArticle("article_056"), profile);
    expect(neg.decision).not.toBe("hidden");
    expect(sig.decision).not.toBe("hidden");
  });

  it("Deni trade article is visible in realistic scenario", () => {
    const draft = inferPreferenceDraftFromCalibration(REALISTIC_RATINGS, calibrationHeadlines);
    const profile = convertCalibrationDraftToUserProfile(draft);
    // article_017 is the Deni trade article
    const result = scoreArticle(getArticle("article_017"), profile);
    expect(result.decision).toBe("push");
  });

  it("Grand Slam winner article is visible when tennis rated positively", () => {
    const draft = inferPreferenceDraftFromCalibration(REALISTIC_RATINGS, calibrationHeadlines);
    const profile = convertCalibrationDraftToUserProfile(draft);
    // article_027 is Grand Slam winner (grand_slam_winner eventType)
    const result = scoreArticle(getArticle("article_027"), profile);
    expect(result.decision).not.toBe("hidden");
  });

  it("early-round tennis result is hidden when only early-round rated not_interesting", () => {
    const draft = inferPreferenceDraftFromCalibration(REALISTIC_RATINGS, calibrationHeadlines);
    const profile = convertCalibrationDraftToUserProfile(draft);
    // article_028 is Alcaraz early-round Wimbledon result
    const result = scoreArticle(getArticle("article_028"), profile);
    expect(result.decision).toBe("hidden");
  });

  it("negative Hornets/Wizards rating does not hide Deni articles when Deni is also rated", () => {
    // Rating Deni positively + generic NBA negatively should NOT mute basketball
    const draft = inferPreferenceDraftFromCalibration({
      cal_012: "push",           // Deni trade — positive
      cal_011: "not_interesting" // Hornets/Wizards — negative
    }, calibrationHeadlines);
    const profile = convertCalibrationDraftToUserProfile(draft);
    // Basketball should NOT be in mutedTopics (NBA topic has 1 positive)
    expect(profile.mutedTopics).not.toContain("basketball");
    // Deni trade article must be visible
    const result = scoreArticle(getArticle("article_017"), profile);
    expect(result.decision).not.toBe("hidden");
  });

  it("muted candidates do not wipe out unrelated positive basketball interest", () => {
    // NBA rated all-negative → mutedCandidates would include "basketball"
    // EuroLeague rated positively → basketball has positive interest → should NOT be muted
    const draft = inferPreferenceDraftFromCalibration({
      cal_011: "not_interesting", // NBA, negative only → NBA topic all-negative
      cal_007: "interesting"      // EuroLeague major signing, positive → priority 85
    }, calibrationHeadlines);
    const profile = convertCalibrationDraftToUserProfile(draft);
    // Basketball must NOT be muted because EuroLeague has priority > 15
    expect(profile.mutedTopics).not.toContain("basketball");
    // At least one EuroLeague article should be visible
    const euroVisible = mockArticles
      .filter(a => a.sport === "basketball" && a.league === "EuroLeague")
      .some(a => scoreArticle(a, profile).decision !== "hidden");
    expect(euroVisible).toBe(true);
  });
});
