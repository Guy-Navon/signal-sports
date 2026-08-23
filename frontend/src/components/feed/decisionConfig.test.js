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

// The Orbit queue must encode ranking visually. These lock the contract that
// orbit.css renders — a level can never silently become a twin of its neighbour.
describe("decisionConfig — Orbit presentation", () => {
  const VISIBLE = ["push", "high_feed", "feed", "low_feed"];

  it("defines a complete orbit block for every decision", () => {
    for (const d of DECISIONS) {
      const o = DECISION_CONFIG[d].orbit;
      expect(o, d).toBeDefined();
      expect(typeof o.queueScale, d).toBe("number");
      expect(["full", "standard", "compact"], d).toContain(o.queueDensity);
      expect(typeof o.queueRail, d).toBe("boolean");
      expect(typeof o.queueMuted, d).toBe("boolean");
    }
  });

  it("orders the queue type scale push > high_feed > feed > low_feed", () => {
    const scale = (d) => DECISION_CONFIG[d].orbit.queueScale;
    expect(scale("push")).toBeGreaterThan(scale("high_feed"));
    expect(scale("high_feed")).toBeGreaterThan(scale("feed"));
    expect(scale("feed")).toBeGreaterThan(scale("low_feed"));
    expect(scale("low_feed")).toBeGreaterThan(scale("hidden"));
  });

  it("keeps queueScale consistent with strength", () => {
    for (const d of DECISIONS) {
      expect(DECISION_CONFIG[d].orbit.queueScale, d).toBe(DECISION_CONFIG[d].strength);
    }
  });

  it("reserves the queue rail for push", () => {
    expect(DECISION_CONFIG.push.orbit.queueRail).toBe(true);
    for (const d of ["high_feed", "feed", "low_feed", "hidden"]) {
      expect(DECISION_CONFIG[d].orbit.queueRail, d).toBe(false);
    }
  });

  it("thins density as relevance drops, never the other way", () => {
    const weight = { full: 2, standard: 1, compact: 0 };
    const density = (d) => weight[DECISION_CONFIG[d].orbit.queueDensity];
    expect(density("push")).toBeGreaterThanOrEqual(density("high_feed"));
    expect(density("high_feed")).toBeGreaterThan(density("feed"));
    expect(density("feed")).toBeGreaterThan(density("low_feed"));
  });

  it("mutes only the levels below feed", () => {
    for (const d of ["push", "high_feed", "feed"]) {
      expect(DECISION_CONFIG[d].orbit.queueMuted, d).toBe(false);
    }
    expect(DECISION_CONFIG.low_feed.orbit.queueMuted).toBe(true);
  });

  // The defect this scope fixes: feed and low_feed rendered identically, so the
  // only difference was the word on the card.
  it("gives every visible level a distinct visual signature", () => {
    const signature = (d) => {
      const { orbit, tone } = DECISION_CONFIG[d];
      return [tone, orbit.queueScale, orbit.queueDensity, orbit.queueRail, orbit.queueMuted].join("|");
    };
    const seen = VISIBLE.map(signature);
    expect(new Set(seen).size).toBe(VISIBLE.length);
  });

  it("separates feed from low_feed on more than one axis", () => {
    const a = DECISION_CONFIG.feed.orbit;
    const b = DECISION_CONFIG.low_feed.orbit;
    const differences = [
      a.queueScale !== b.queueScale,
      a.queueDensity !== b.queueDensity,
      a.queueMuted !== b.queueMuted,
    ].filter(Boolean);
    expect(differences.length).toBeGreaterThanOrEqual(2);
  });

  it("gives every visible level its own tone so no two share a colour", () => {
    const tones = VISIBLE.map((d) => DECISION_CONFIG[d].tone);
    expect(new Set(tones).size).toBe(VISIBLE.length);
  });
});
