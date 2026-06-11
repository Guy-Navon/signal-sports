import { describe, it, expect } from "vitest";
import { calibrationHeadlines } from "../data/calibrationHeadlines";
import { mockArticles } from "../data/mockArticles";
import { scoreArticle } from "./relevanceEngine";
import { userProfiles } from "../data/userProfiles";

const guy = userProfiles.guy;
const deni = userProfiles.casual_deni_fan;

function findArticle(id) {
  const a = mockArticles.find(a => a.id === id);
  if (!a) throw new Error(`Article ${id} not found`);
  return a;
}

function scoreDecision(articleId, profile) {
  return scoreArticle(findArticle(articleId), profile).decision;
}

// ─────────────────────────────────────────────────────────────────────────────
// Dataset size requirements
// ─────────────────────────────────────────────────────────────────────────────

describe("Dataset size requirements", () => {
  it("calibrationHeadlines has at least 40 items", () => {
    expect(calibrationHeadlines.length).toBeGreaterThanOrEqual(40);
  });

  it("mockArticles has at least 60 items", () => {
    expect(mockArticles.length).toBeGreaterThanOrEqual(60);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// calibrationHeadlines topic coverage
// ─────────────────────────────────────────────────────────────────────────────

describe("Calibration headline topic coverage", () => {
  it("has at least 5 NBA headlines", () => {
    const nba = calibrationHeadlines.filter(h => h.league === "NBA");
    expect(nba.length).toBeGreaterThanOrEqual(5);
  });

  it("has at least 5 Maccabi or EuroLeague basketball headlines", () => {
    const maccabiOrEL = calibrationHeadlines.filter(h =>
      h.league === "EuroLeague" ||
      (h.entities || []).includes("Maccabi Tel Aviv Basketball")
    );
    expect(maccabiOrEL.length).toBeGreaterThanOrEqual(5);
  });

  it("has at least 3 tennis headlines", () => {
    const tennis = calibrationHeadlines.filter(h => h.sport === "tennis");
    expect(tennis.length).toBeGreaterThanOrEqual(3);
  });

  it("has at least 3 football headlines", () => {
    const football = calibrationHeadlines.filter(h => h.sport === "football");
    expect(football.length).toBeGreaterThanOrEqual(3);
  });

  it("has at least 3 European domestic basketball headlines", () => {
    const europeanLeagues = ["Spanish ACB", "Turkish BSL", "Greek Basket League", "Italian LBA", "French LNB"];
    const euDomestic = calibrationHeadlines.filter(h => europeanLeagues.includes(h.league));
    expect(euDomestic.length).toBeGreaterThanOrEqual(3);
  });

  it("has no duplicate IDs", () => {
    const ids = calibrationHeadlines.map(h => h.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(ids.length);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// mockArticles: profile divergence — same article, different decisions
// ─────────────────────────────────────────────────────────────────────────────

describe("Profile divergence: Guy sees NBA content Casual Deni Fan does not", () => {
  it("Warriors vs Bucks regular season: Guy→feed, Deni Fan→hidden", () => {
    expect(scoreDecision("article_042", guy)).toBe("feed");
    expect(scoreDecision("article_042", deni)).toBe("hidden");
  });

  it("NBA playoff (Celtics/Heat, no Deni): Guy→high_feed, Deni Fan→hidden", () => {
    expect(scoreDecision("article_044", guy)).toBe("high_feed");
    expect(scoreDecision("article_044", deni)).toBe("hidden");
  });

  it("NBA mid-level trade (no Deni): Guy→high_feed, Deni Fan→hidden", () => {
    expect(scoreDecision("article_048", guy)).toBe("high_feed");
    expect(scoreDecision("article_048", deni)).toBe("hidden");
  });
});

describe("Profile divergence: Deni-specific content visible to both profiles", () => {
  it("Deni injury: push for both — entity-specific push rule applies to all push-eligible events", () => {
    // injury is in PUSH_ELIGIBLE_EVENT_TYPES; entity key "deni_avdija_trade" exists → push
    expect(scoreDecision("article_046", guy)).toBe("push");
    expect(scoreDecision("article_046", deni)).toBe("push");
  });

  it("Deni career-high performance: Guy→high_feed (entity boost), Deni Fan→feed", () => {
    expect(scoreDecision("article_047", guy)).toBe("high_feed");
    expect(scoreDecision("article_047", deni)).toBe("feed");
  });

  it("Deni trade: push for both profiles", () => {
    // article_017 is the existing Deni trade article
    expect(scoreDecision("article_017", guy)).toBe("push");
    expect(scoreDecision("article_017", deni)).toBe("push");
  });
});

describe("Profile divergence: non-basketball content", () => {
  it("Maccabi signing: Guy→push, Deni Fan→hidden", () => {
    expect(scoreDecision("article_056", guy)).toBe("push");
    expect(scoreDecision("article_056", deni)).toBe("hidden");
  });

  it("EuroLeague Final Four: Guy→high_feed, Deni Fan→hidden", () => {
    expect(scoreDecision("article_054", guy)).toBe("high_feed");
    expect(scoreDecision("article_054", deni)).toBe("hidden");
  });

  it("Tennis Grand Slam final: Guy→feed, Deni Fan→hidden", () => {
    expect(scoreDecision("article_066", guy)).toBe("feed");
    expect(scoreDecision("article_066", deni)).toBe("hidden");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// mockArticles: noise suppression for Guy
// ─────────────────────────────────────────────────────────────────────────────

describe("Noise suppression — Guy sees at most low-value for noise articles", () => {
  it("NBA schedule is hidden for Guy", () => {
    expect(scoreDecision("article_049", guy)).toBe("hidden");
  });

  it("NBA pre-match lineup (very_low importance) is hidden for Guy", () => {
    expect(scoreDecision("article_050", guy)).toBe("hidden");
  });

  it("Football schedule is hidden for Guy", () => {
    expect(scoreDecision("article_051", guy)).toBe("hidden");
  });

  it("Maccabi schedule is hidden for Guy", () => {
    expect(scoreDecision("article_058", guy)).toBe("hidden");
  });

  it("Maccabi pre-match lineup (very_low importance) is hidden for Guy", () => {
    expect(scoreDecision("article_059", guy)).toBe("hidden");
  });

  it("Greek basketball league schedule is hidden for Guy", () => {
    expect(scoreDecision("article_065", guy)).toBe("hidden");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Aggregate counts: Guy's feed quality
// ─────────────────────────────────────────────────────────────────────────────

describe("Aggregate dataset quality for Guy's profile", () => {
  it("at least 10 articles score as hidden for Guy (noise suppression working)", () => {
    const hiddenCount = mockArticles.filter(
      a => scoreArticle(a, guy).decision === "hidden"
    ).length;
    expect(hiddenCount).toBeGreaterThanOrEqual(10);
  });

  it("at least 5 articles score as push for Guy (high-value signal present)", () => {
    const pushCount = mockArticles.filter(
      a => scoreArticle(a, guy).decision === "push"
    ).length;
    expect(pushCount).toBeGreaterThanOrEqual(5);
  });

  it("mockArticles has no duplicate IDs", () => {
    const ids = mockArticles.map(a => a.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(ids.length);
  });
});
