import { describe, it, expect } from "vitest";
import { scoreArticle, DECISION_RANK } from "./relevanceEngine";
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
    // article_017: Deni Avdija major_trade — entity-specific deni_avdija_trade rule = push
    const result = scoreArticle(getArticle("article_017"), guy);
    expect(result.decision).toBe("push");
  });

  it("Deni Avdija trade is push for Casual Deni Fan", () => {
    // article_017: Deni is the entity match — deni_avdija_trade rule = push
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
