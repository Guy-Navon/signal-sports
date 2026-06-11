import { describe, it, expect } from "vitest";
import { inferPreferenceDraftFromCalibration } from "./calibrationEngine";
import { calibrationHeadlines } from "../data/calibrationHeadlines";

// Helper: run inference with a subset of ratings
function infer(ratingMap) {
  return inferPreferenceDraftFromCalibration(ratingMap, calibrationHeadlines);
}

// Helper: find a topic in the draft by sport + optional league
function findTopic(draft, sport, league) {
  return draft.inferredTopics.find(
    t => t.sport === sport && (league === undefined || t.league === league)
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Event rule inference from individual ratings
// ─────────────────────────────────────────────────────────────────────────────

describe("Rating Maccabi negotiation as push", () => {
  it("creates a negotiation → push event rule for the EuroLeague topic", () => {
    // cal_001: Maccabi TLV negotiation, EuroLeague
    const draft = infer({ cal_001: "push" });
    const topic = findTopic(draft, "basketball", "EuroLeague");
    expect(topic).toBeDefined();
    expect(topic.eventRules.negotiation).toBe("push");
  });

  it("includes Maccabi Tel Aviv Basketball in the topic entities", () => {
    const draft = infer({ cal_001: "push" });
    const topic = findTopic(draft, "basketball", "EuroLeague");
    expect(topic.entities).toContain("Maccabi Tel Aviv Basketball");
  });
});

describe("Rating Maccabi friendly match as neutral", () => {
  it("creates a friendly_match → low_feed event rule", () => {
    // cal_006: Maccabi friendly match, Israeli Basketball League
    const draft = infer({ cal_006: "neutral" });
    const topic = findTopic(draft, "basketball", "Israeli Basketball League");
    expect(topic).toBeDefined();
    expect(topic.eventRules.friendly_match).toBe("low_feed");
  });
});

describe("Rating Alcaraz early-round result as not_interesting", () => {
  it("creates an early_round_result → hidden event rule for tennis", () => {
    // cal_022: Alcaraz early round, Grand Slam
    const draft = infer({ cal_022: "not_interesting" });
    const topic = findTopic(draft, "tennis", "Grand Slam");
    expect(topic).toBeDefined();
    expect(topic.eventRules.early_round_result).toBe("hidden");
  });
});

describe("Rating Grand Slam winner as interesting", () => {
  it("creates a grand_slam_winner → high_feed event rule", () => {
    // cal_021: Alcaraz Grand Slam win
    const draft = infer({ cal_021: "interesting" });
    const topic = findTopic(draft, "tennis", "Grand Slam");
    expect(topic).toBeDefined();
    expect(["feed", "high_feed"]).toContain(topic.eventRules.grand_slam_winner);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Mode inference from rating patterns
// ─────────────────────────────────────────────────────────────────────────────

describe("Rating Hornets vs Wizards as interesting", () => {
  it("creates an NBA topic with mode 'all' (broad NBA interest)", () => {
    // cal_011: Hornets vs Wizards, NBA regular season — no Deni
    const draft = infer({ cal_011: "interesting" });
    const topic = findTopic(draft, "basketball", "NBA");
    expect(topic).toBeDefined();
    // A single positive rating with no negative contrast → broad mode
    expect(topic.mode).toBe("all");
  });

  it("creates a regular_season_result event rule for the NBA topic", () => {
    const draft = infer({ cal_011: "interesting" });
    const topic = findTopic(draft, "basketball", "NBA");
    expect(topic.eventRules.regular_season_result).toBeDefined();
    expect(["feed", "high_feed"]).toContain(topic.eventRules.regular_season_result);
  });
});

describe("Rating Hornets vs Wizards as not_interesting and Deni trade as push", () => {
  it("infers followed_entities_only mode for NBA (entity-focused interest)", () => {
    // cal_011: Hornets/Wizards (no Deni) → not_interesting
    // cal_012: Deni trade → push
    const draft = infer({ cal_011: "not_interesting", cal_012: "push" });
    const topic = findTopic(draft, "basketball", "NBA");
    expect(topic).toBeDefined();
    expect(topic.mode).toBe("followed_entities_only");
  });

  it("includes Deni Avdija in followedEntities", () => {
    const draft = infer({ cal_011: "not_interesting", cal_012: "push" });
    expect(draft.followedEntities).toContain("Deni Avdija");
  });

  it("does NOT include Charlotte Hornets in followedEntities", () => {
    const draft = infer({ cal_011: "not_interesting", cal_012: "push" });
    expect(draft.followedEntities).not.toContain("Charlotte Hornets");
  });

  it("creates push rule for major_trade and hidden rule for regular_season_result", () => {
    const draft = infer({ cal_011: "not_interesting", cal_012: "push" });
    const topic = findTopic(draft, "basketball", "NBA");
    expect(topic.eventRules.major_trade).toBe("push");
    expect(topic.eventRules.regular_season_result).toBe("hidden");
  });
});

describe("Rating small Israeli football result as never_show", () => {
  it("adds football to mutedCandidates", () => {
    // cal_025: small Israeli football result (never_show → mute candidate)
    const draft = infer({ cal_025: "never_show" });
    expect(draft.mutedCandidates).toContain("football");
  });

  it("creates a hidden event rule for the football topic", () => {
    const draft = infer({ cal_025: "never_show" });
    const topic = findTopic(draft, "football");
    expect(topic).toBeDefined();
    expect(topic.eventRules.regular_season_result).toBe("hidden");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Edge cases
// ─────────────────────────────────────────────────────────────────────────────

describe("Empty ratings", () => {
  it("returns empty draft with a Hebrew placeholder message", () => {
    const draft = infer({});
    expect(draft.inferredTopics).toHaveLength(0);
    expect(draft.followedEntities).toHaveLength(0);
    expect(draft.mutedCandidates).toHaveLength(0);
    expect(draft.reasoning).toHaveLength(1);
  });
});

describe("Highest-ranking rule wins for same eventType", () => {
  it("push beats interesting when both rate the same eventType in the same topic", () => {
    // cal_001: Maccabi negotiation → push
    // cal_004: Maccabi candidate (different event, but same topic)
    // Rate both — cal_001 push should dominate its eventType
    const draft = infer({ cal_001: "push", cal_004: "interesting" });
    const topic = findTopic(draft, "basketball", "EuroLeague");
    expect(topic.eventRules.negotiation).toBe("push");
    expect(topic.eventRules.candidate).toBe("high_feed");
  });
});

describe("titles_only mode inference for tennis", () => {
  it("infers titles_only when Grand Slam winner is interesting but early round is not_interesting", () => {
    // cal_021: Grand Slam winner → interesting
    // cal_022: early round → not_interesting
    const draft = infer({ cal_021: "interesting", cal_022: "not_interesting" });
    const topic = findTopic(draft, "tennis", "Grand Slam");
    expect(topic).toBeDefined();
    expect(topic.mode).toBe("titles_only");
  });
});
