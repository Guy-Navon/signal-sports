import { describe, it, expect } from "vitest";
import { scoreArticle, doesTopicMatchArticle, DECISION_RANK } from "./relevanceEngine";
import { userProfiles } from "../data/userProfiles";
import { mockArticles } from "../data/mockArticles";

const guy = userProfiles.guy;
const denieFan = userProfiles.casual_deni_fan;

function getArticle(id) {
  const article = mockArticles.find(a => a.id === id);
  if (!article) throw new Error(`Article ${id} not found in mockArticles`);
  return article;
}

// ─────────────────────────────────────────────────────────────────
// Maccabi Tel Aviv Basketball
// ─────────────────────────────────────────────────────────────────
describe("Maccabi Tel Aviv Basketball — Guy", () => {
  it("negotiation is push", () => {
    // article_037: standalone Maccabi negotiation (EuroLeague, high importance)
    const result = scoreArticle(getArticle("article_037"), guy);
    expect(result.decision).toBe("push");
  });

  it("injury is push", () => {
    // article_005: Maccabi player injury (Israeli Basketball League, high importance)
    const result = scoreArticle(getArticle("article_005"), guy);
    expect(result.decision).toBe("push");
  });

  it("candidate/rumor is high_feed, not push", () => {
    // article_006: Maccabi interested in Serbian forward — candidate, medium importance
    const result = scoreArticle(getArticle("article_006"), guy);
    expect(result.decision).toBe("high_feed");
    expect(result.decision).not.toBe("push");
  });

  it("schedule/broadcast article is hidden", () => {
    // article_040: broadcast schedule, very_low importance — explicit schedule rule = hidden
    const result = scoreArticle(getArticle("article_040"), guy);
    expect(result.decision).toBe("hidden");
  });
});

// ─────────────────────────────────────────────────────────────────
// NBA — per-profile divergence
// ─────────────────────────────────────────────────────────────────
describe("NBA — profile-dependent decisions", () => {
  it("Hornets vs Wizards regular-season result is visible for Guy", () => {
    // article_015: no Deni, no Maccabi — should appear for Guy (NBA all mode, regular_season_result → feed)
    const result = scoreArticle(getArticle("article_015"), guy);
    expect(result.decision).not.toBe("hidden");
    expect(DECISION_RANK[result.decision]).toBeGreaterThan(DECISION_RANK["hidden"]);
  });

  it("Hornets vs Wizards regular-season result is hidden for Casual Deni Fan", () => {
    // article_015: Deni not mentioned — followed_entities_only mode hides this
    const result = scoreArticle(getArticle("article_015"), denieFan);
    expect(result.decision).toBe("hidden");
  });

  it("Deni Avdija trade is push for Guy", () => {
    // article_017: Deni major_trade — entityEventRules["Deni Avdija"].major_trade = "push"
    const result = scoreArticle(getArticle("article_017"), guy);
    expect(result.decision).toBe("push");
  });

  it("Deni Avdija trade is push for Casual Deni Fan", () => {
    // article_017: Deni entity match — entityEventRules["Deni Avdija"].major_trade = "push"
    const result = scoreArticle(getArticle("article_017"), denieFan);
    expect(result.decision).toBe("push");
  });
});

// ─────────────────────────────────────────────────────────────────
// Tennis — titles_only mode
// ─────────────────────────────────────────────────────────────────
describe("Tennis — Guy (titles_only mode)", () => {
  it("Grand Slam winner is high_feed", () => {
    // article_027: Alcaraz wins Grand Slam — grand_slam_winner rule = high_feed
    const result = scoreArticle(getArticle("article_027"), guy);
    expect(result.decision).toBe("high_feed");
  });

  it("Alcaraz early-round result is hidden", () => {
    // article_028: Wimbledon first round — early_round_result rule = hidden
    const result = scoreArticle(getArticle("article_028"), guy);
    expect(result.decision).toBe("hidden");
  });
});

// ─────────────────────────────────────────────────────────────────
// Pre-match / generic content
// ─────────────────────────────────────────────────────────────────
describe("Generic low-value content", () => {
  it("schedule/broadcast article is hidden for Guy", () => {
    // article_040: broadcast schedule content — schedule rule = hidden
    const result = scoreArticle(getArticle("article_040"), guy);
    expect(result.decision).toBe("hidden");
  });

  it("NBA generic preview is low_feed for Guy, hidden for Casual Deni Fan", () => {
    // article_020: Lakers preview — generic_preview = low_feed for Guy; no Deni = hidden for casual fan
    expect(scoreArticle(getArticle("article_020"), guy).decision).toBe("low_feed");
    expect(scoreArticle(getArticle("article_020"), denieFan).decision).toBe("hidden");
  });
});

// ─────────────────────────────────────────────────────────────────
// Muting
// ─────────────────────────────────────────────────────────────────
describe("Muting behavior", () => {
  it("muted source returns hidden", () => {
    // article_015 comes from "sportando" — muting sportando must hide it
    const profile = { ...guy, mutedSources: ["sportando"] };
    const result = scoreArticle(getArticle("article_015"), profile);
    expect(result.decision).toBe("hidden");
  });

  it("muted topic returns hidden", () => {
    // article_015 has league "NBA" — muting "NBA" must hide it
    const profile = { ...guy, mutedTopics: ["NBA"] };
    const result = scoreArticle(getArticle("article_015"), profile);
    expect(result.decision).toBe("hidden");
  });

  it("disabled source (Sources page) returns hidden", () => {
    // passing disabledSourceIds simulates a source being toggled off on the Sources page
    const disabledSourceIds = new Set(["sportando"]);
    const result = scoreArticle(getArticle("article_015"), guy, { disabledSourceIds });
    expect(result.decision).toBe("hidden");
  });
});

// ─────────────────────────────────────────────────────────────────
// Push discipline — importance boost alone never produces push
// ─────────────────────────────────────────────────────────────────
describe("Push discipline", () => {
  it("very_high importance does not auto-escalate to push — hard cap at high_feed", () => {
    // article_018: NBA Finals result (very_high importance, finals_result = high_feed for Guy)
    // importance boost should NOT elevate this to push
    const result = scoreArticle(getArticle("article_018"), guy);
    expect(result.decision).toBe("high_feed");
    expect(result.decision).not.toBe("push");
  });

  it("NBA record (very_high importance) caps at high_feed for Guy", () => {
    // article_019: NBA player breaks 40-year record, very_high importance, record = high_feed
    const result = scoreArticle(getArticle("article_019"), guy);
    expect(result.decision).toBe("high_feed");
    expect(result.decision).not.toBe("push");
  });

  it("Maccabi title win is push — only because of explicit push event rule", () => {
    // article_014: Maccabi wins State Cup — title_win rule = push
    // This tests that push IS reachable when explicitly declared
    const result = scoreArticle(getArticle("article_014"), guy);
    expect(result.decision).toBe("push");
  });
});

// ─────────────────────────────────────────────────────────────────
// importanceFallback noise prevention
// ─────────────────────────────────────────────────────────────────
describe("importanceFallback — noise prevention", () => {
  it("very_low importance article with no event rule is hidden", () => {
    // Synthetic article: sport matches a topic but eventType has no rule, very_low importance
    const article = {
      id: "test_very_low",
      source: "sport5",
      sport: "basketball",
      league: "Israeli Basketball League",
      entities: [],
      eventType: "unknown_event_type",
      importance: "very_low",
      confidence: 0.5,
      tags: [],
      clusterId: null
    };
    const result = scoreArticle(article, guy);
    expect(result.decision).toBe("hidden");
  });

  it("low importance article hitting low-priority topic (priority < 70) is hidden", () => {
    // Football topic has priority 20 — low importance with no event rule should be hidden
    const article = {
      id: "test_low_low_priority",
      source: "walla",
      sport: "football",
      league: "Israeli Premier League",
      entities: [],
      eventType: "unknown_event_type",
      importance: "low",
      confidence: 0.5,
      tags: [],
      clusterId: null
    };
    const result = scoreArticle(article, guy);
    expect(result.decision).toBe("hidden");
  });
});

// ─────────────────────────────────────────────────────────────────
// entityEventRules — entity-specific event overrides
// ─────────────────────────────────────────────────────────────────
describe("entityEventRules — entity-specific event overrides", () => {
  it("Deni injury is push for Guy via entityEventRules (not generic injury: feed)", () => {
    // article_046: injury + Deni entity — entityEventRules["Deni Avdija"].injury = "push"
    // without entityEventRules, generic NBA injury: "feed" would apply
    const result = scoreArticle(getArticle("article_046"), guy);
    expect(result.decision).toBe("push");
  });

  it("non-Deni NBA major trade is high_feed for Guy (generic rule, not entity override)", () => {
    // article_048: Miami/Wolves major_trade, no Deni — generic major_trade: "high_feed"
    const result = scoreArticle(getArticle("article_048"), guy);
    expect(result.decision).toBe("high_feed");
  });

  it("Deni career-high performance is high_feed for Casual Deni Fan via entityEventRules", () => {
    // article_047: Deni 35pts regular_season_result — entityEventRules overrides generic "feed"
    const result = scoreArticle(getArticle("article_047"), denieFan);
    expect(result.decision).toBe("high_feed");
  });

  it("Deni injury is push for Casual Deni Fan via entityEventRules", () => {
    // article_046: Deni injury — entityEventRules["Deni Avdija"].injury = "push"
    const result = scoreArticle(getArticle("article_046"), denieFan);
    expect(result.decision).toBe("push");
  });

  it("profile data: Guy NBA topic has no legacy deni_avdija_trade key", () => {
    const nbaTopic = guy.topics.find(t => t.topicId === "nba");
    expect(nbaTopic.eventRules.deni_avdija_trade).toBeUndefined();
  });

  it("profile data: Casual Deni Fan NBA topic has no legacy deni_avdija_trade key", () => {
    const nbaTopic = denieFan.topics.find(t => t.topicId === "nba");
    expect(nbaTopic.eventRules.deni_avdija_trade).toBeUndefined();
  });

  it("profile data: Casual Deni Fan NBA topic has no legacy deni_avdija_news key", () => {
    const nbaTopic = denieFan.topics.find(t => t.topicId === "nba");
    expect(nbaTopic.eventRules.deni_avdija_news).toBeUndefined();
  });

  it("profile data: both NBA topics have entityEventRules for Deni Avdija", () => {
    const guyNba = guy.topics.find(t => t.topicId === "nba");
    const deniNba = denieFan.topics.find(t => t.topicId === "nba");
    expect(guyNba.entityEventRules?.["Deni Avdija"]).toBeDefined();
    expect(deniNba.entityEventRules?.["Deni Avdija"]).toBeDefined();
  });
});

// ─────────────────────────────────────────────────────────────────
// Topic Scope Guards — doesTopicMatchArticle unit tests
// ─────────────────────────────────────────────────────────────────
describe("Topic scope guards — doesTopicMatchArticle()", () => {
  const maccabiTopic = guy.topics.find(t => t.topicId === "maccabi_tel_aviv_basketball");
  const nbaTopic = guy.topics.find(t => t.topicId === "nba");
  const euroleagueTopic = guy.topics.find(t => t.topicId === "euroleague");
  const europeanDomesticTopic = guy.topics.find(t => t.topicId === "major_european_domestic_basketball");
  const footballTopic = guy.topics.find(t => t.topicId === "football");
  const tennisTopic = guy.topics.find(t => t.topicId === "tennis");

  it("profile topics have expected scope values", () => {
    expect(maccabiTopic.scope).toBe("entity");
    expect(nbaTopic.scope).toBe("league");
    expect(euroleagueTopic.scope).toBe("league");
    expect(europeanDomesticTopic.scope).toBe("league_group");
    expect(footballTopic.scope).toBe("sport");
    expect(tennisTopic.scope).toBe("sport");
  });

  it("entity scope: Maccabi topic matches article with Maccabi entity", () => {
    const article = {
      sport: "basketball", league: "EuroLeague",
      entities: ["Maccabi Tel Aviv Basketball"], eventType: "negotiation", importance: "high"
    };
    expect(doesTopicMatchArticle(article, maccabiTopic).matched).toBe(true);
  });

  it("entity scope: Maccabi topic does NOT match non-Maccabi basketball article (sport alone insufficient)", () => {
    const article = {
      sport: "basketball", league: "EuroLeague",
      entities: ["Real Madrid Basketball"], eventType: "major_transfer", importance: "high"
    };
    expect(doesTopicMatchArticle(article, maccabiTopic).matched).toBe(false);
  });

  it("entity scope: Maccabi topic does NOT match non-Maccabi Spanish ACB article", () => {
    const article = {
      sport: "basketball", league: "Spanish ACB",
      entities: ["Real Madrid Basketball"], eventType: "playoff_result", importance: "high"
    };
    expect(doesTopicMatchArticle(article, maccabiTopic).matched).toBe(false);
  });

  it("league scope: NBA topic matches article with league NBA", () => {
    const article = {
      sport: "basketball", league: "NBA",
      entities: ["Charlotte Hornets", "Washington Wizards"], eventType: "regular_season_result", importance: "low"
    };
    expect(doesTopicMatchArticle(article, nbaTopic).matched).toBe(true);
  });

  it("league scope: NBA topic does NOT match EuroLeague article", () => {
    const article = {
      sport: "basketball", league: "EuroLeague",
      entities: ["Fenerbahce"], eventType: "match_result", importance: "medium"
    };
    expect(doesTopicMatchArticle(article, nbaTopic).matched).toBe(false);
  });

  it("league scope: EuroLeague topic matches EuroLeague article without Maccabi entity", () => {
    const article = {
      sport: "basketball", league: "EuroLeague",
      entities: ["Real Madrid Basketball"], eventType: "major_transfer", importance: "high"
    };
    expect(doesTopicMatchArticle(article, euroleagueTopic).matched).toBe(true);
  });

  it("league_group scope: European domestic topic matches Spanish ACB article", () => {
    const article = {
      sport: "basketball", league: "Spanish ACB",
      entities: ["Real Madrid Basketball"], eventType: "playoff_result", importance: "high"
    };
    expect(doesTopicMatchArticle(article, europeanDomesticTopic).matched).toBe(true);
  });

  it("league_group scope: European domestic topic matches Turkish BSL article", () => {
    const article = {
      sport: "basketball", league: "Turkish BSL",
      entities: ["Fenerbahce"], eventType: "match_result", importance: "medium"
    };
    expect(doesTopicMatchArticle(article, europeanDomesticTopic).matched).toBe(true);
  });

  it("league_group scope: European domestic topic does NOT match NBA article", () => {
    const article = {
      sport: "basketball", league: "NBA",
      entities: ["Charlotte Hornets"], eventType: "regular_season_result", importance: "low"
    };
    expect(doesTopicMatchArticle(article, europeanDomesticTopic).matched).toBe(false);
  });

  it("sport scope: football topic matches any football article", () => {
    const article = {
      sport: "football", league: "Israeli Premier League",
      entities: [], eventType: "regular_season_result", importance: "low"
    };
    expect(doesTopicMatchArticle(article, footballTopic).matched).toBe(true);
  });

  it("sport scope: football topic does NOT match basketball article", () => {
    const article = {
      sport: "basketball", league: "NBA",
      entities: [], eventType: "regular_season_result", importance: "low"
    };
    expect(doesTopicMatchArticle(article, footballTopic).matched).toBe(false);
  });

  it("sport scope: tennis topic matches tennis article regardless of league", () => {
    const article = {
      sport: "tennis", league: "Wimbledon",
      entities: ["Carlos Alcaraz"], eventType: "early_round_result", importance: "low"
    };
    expect(doesTopicMatchArticle(article, tennisTopic).matched).toBe(true);
  });

  it("legacy (no scope): falls back to OR matching — sport match", () => {
    const legacyTopic = { sport: "basketball", leagues: [], entities: [] }; // no scope field
    const article = { sport: "basketball", league: "NBA", entities: [] };
    expect(doesTopicMatchArticle(article, legacyTopic).matched).toBe(true);
  });

  it("legacy (no scope): falls back to OR matching — league match", () => {
    const legacyTopic = { sport: "football", leagues: ["EuroLeague"], entities: [] };
    const article = { sport: "basketball", league: "EuroLeague", entities: [] };
    expect(doesTopicMatchArticle(article, legacyTopic).matched).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────
// Topic Scope Guards — end-to-end scoring consequences
// ─────────────────────────────────────────────────────────────────
describe("Topic scope guards — end-to-end scoring", () => {
  it("non-Maccabi EuroLeague major transfer is NOT push (Maccabi scope guard blocks it)", () => {
    const article = {
      id: "test_nonmaccabi_el_transfer",
      source: "eurohoops",
      sport: "basketball",
      league: "EuroLeague",
      entities: ["Real Madrid Basketball"],
      eventType: "major_transfer",
      importance: "high",
      confidence: 0.93,
      tags: [],
      clusterId: null
    };
    const result = scoreArticle(article, guy);
    expect(result.decision).not.toBe("push");
    expect(result.decision).toBe("high_feed"); // EuroLeague topic: major_transfer → high_feed
  });

  it("non-Maccabi EuroLeague major transfer matches EuroLeague topic (not Maccabi topic)", () => {
    const article = {
      id: "test_nonmaccabi_el_transfer",
      source: "eurohoops",
      sport: "basketball",
      league: "EuroLeague",
      entities: ["Real Madrid Basketball"],
      eventType: "major_transfer",
      importance: "high",
      confidence: 0.93,
      tags: [],
      clusterId: null
    };
    const result = scoreArticle(article, guy);
    // Must be matched by EuroLeague topic, not maccabi_tel_aviv_basketball
    expect(result.matchedTopic).toBe("euroleague");
  });

  it("Maccabi EuroLeague signing is still push (entity scope matches, explicit push rule applies)", () => {
    // article_056: Maccabi signing in EuroLeague — entities include Maccabi
    const result = scoreArticle(getArticle("article_056"), guy);
    expect(result.decision).toBe("push");
  });

  it("Maccabi EuroLeague negotiation is still push (article_037)", () => {
    const result = scoreArticle(getArticle("article_037"), guy);
    expect(result.decision).toBe("push");
  });

  it("Maccabi injury is still push despite entity-only scope (article_005)", () => {
    const result = scoreArticle(getArticle("article_005"), guy);
    expect(result.decision).toBe("push");
  });

  it("NBA broad topic still shows regular season for Guy (league scope matches)", () => {
    // article_015: Hornets vs Wizards, NBA league
    const result = scoreArticle(getArticle("article_015"), guy);
    expect(result.decision).not.toBe("hidden");
  });

  it("Casual Deni Fan still hides unrelated NBA articles (followed_entities_only + league scope)", () => {
    // article_015: Hornets vs Wizards — no Deni entity
    const result = scoreArticle(getArticle("article_015"), denieFan);
    expect(result.decision).toBe("hidden");
  });

  it("non-Maccabi EuroLeague article is hidden for Casual Deni Fan (league not matched by NBA-only profile)", () => {
    const article = {
      id: "test_el_fenerbahce",
      source: "eurohoops",
      sport: "basketball",
      league: "EuroLeague",
      entities: ["Fenerbahce"],
      eventType: "final_four",
      importance: "very_high",
      confidence: 0.99,
      tags: [],
      clusterId: null
    };
    // Deni Fan only has NBA topic — EuroLeague articles have no matching topic
    const result = scoreArticle(article, denieFan);
    expect(result.decision).toBe("hidden");
  });

  it("Spanish ACB playoff is visible for Guy via league_group scope (article_062)", () => {
    // article_062 should be the ACB playoff article
    const result = scoreArticle(getArticle("article_062"), guy);
    expect(result.decision).not.toBe("hidden");
  });

  it("Italian LBA generic preview is hidden for Guy (high_importance_only + hidden event rule)", () => {
    const article = {
      id: "test_lba_preview",
      source: "eurohoops",
      sport: "basketball",
      league: "Italian LBA",
      entities: ["Olimpia Milano"],
      eventType: "generic_preview",
      importance: "very_low",
      confidence: 0.75,
      tags: [],
      clusterId: null
    };
    const result = scoreArticle(article, guy);
    expect(result.decision).toBe("hidden");
  });

  it("Turkish BSL derby matches European domestic topic via league_group scope", () => {
    const article = {
      id: "test_bsl_derby",
      source: "eurohoops",
      sport: "basketball",
      league: "Turkish BSL",
      entities: ["Fenerbahce", "Anadolu Efes"],
      eventType: "match_result",
      importance: "high"
    };
    // high_importance_only mode: importance high → passes filter; match_result is hidden in eventRules
    // so importance fallback is used: high + priority 65 → feed
    const result = scoreArticle(article, guy);
    // Should not be push (no explicit push rule in this topic)
    expect(result.decision).not.toBe("push");
    // Should not be hidden — it's a high-importance article in a tracked league
    expect(result.decision).not.toBe("hidden");
  });

  it("Tennis Grand Slam winner still high_feed via sport scope (article_027)", () => {
    const result = scoreArticle(getArticle("article_027"), guy);
    expect(result.decision).toBe("high_feed");
  });

  it("Tennis early-round result still hidden via sport scope + titles_only mode (article_028)", () => {
    const result = scoreArticle(getArticle("article_028"), guy);
    expect(result.decision).toBe("hidden");
  });
});
