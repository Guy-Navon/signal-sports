import { describe, it, expect } from "vitest";
import { DECISION_CONFIG, getDecisionConfig, DECISION_RANK } from "./decisionConfig";
import { normalizeScoredArticleFromApi } from "@/api/normalizers";

const DECISIONS = ["push", "high_feed", "feed", "low_feed", "hidden"];

describe("decisionConfig", () => {
  it("defines every decision level with a complete shape", () => {
    for (const d of DECISIONS) {
      const c = DECISION_CONFIG[d];
      expect(c, d).toBeDefined();
      expect(c.label.length, d).toBeGreaterThan(0);
      expect(c.icon, d).toBeTruthy();
      expect(typeof c.rail, d).toBe("string");
      expect(typeof c.badge, d).toBe("string");
      expect(typeof c.strength, d).toBe("number");
    }
  });

  it("orders signal strength: push > high > feed > low > hidden", () => {
    expect(DECISION_CONFIG.push.strength).toBeGreaterThan(DECISION_CONFIG.high_feed.strength);
    expect(DECISION_CONFIG.high_feed.strength).toBeGreaterThan(DECISION_CONFIG.feed.strength);
    expect(DECISION_CONFIG.feed.strength).toBeGreaterThan(DECISION_CONFIG.low_feed.strength);
    expect(DECISION_CONFIG.low_feed.strength).toBeGreaterThan(DECISION_CONFIG.hidden.strength);
  });

  it("reserves the glow for push only", () => {
    expect(DECISION_CONFIG.push.railGlow).toBe(true);
    for (const d of ["high_feed", "feed", "low_feed", "hidden"]) {
      expect(DECISION_CONFIG[d].railGlow, d).toBeFalsy();
    }
  });

  it("falls back to feed for unknown decisions", () => {
    expect(getDecisionConfig("nonsense")).toBe(DECISION_CONFIG.feed);
    expect(getDecisionConfig(undefined)).toBe(DECISION_CONFIG.feed);
  });

  it("keeps Hebrew labels in sync with the API normalizer labels", () => {
    // normalizeScoredArticleFromApi stamps score.label from DECISION_LABELS_HE;
    // our config labels must match exactly so the UI and API never disagree.
    for (const d of DECISIONS) {
      const normalized = normalizeScoredArticleFromApi({
        decision: d,
        article: { id: "x", source: "walla_sport", title: "t" },
      });
      expect(DECISION_CONFIG[d].label, d).toBe(normalized.score.label);
    }
  });

  it("exposes a rank consistent with strength ordering", () => {
    expect(DECISION_RANK).toMatchObject({ hidden: 0, low_feed: 1, feed: 2, high_feed: 3, push: 4 });
  });
});
