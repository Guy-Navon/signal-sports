import { describe, it, expect } from "vitest";
import { signalStrength, SIGNAL_STROKES } from "./signalStrengthModel";
import { DECISION_CONFIG } from "@/components/feed/decisionConfig";

describe("signalStrength", () => {
  it("fills one stroke per level up to three, push in the alert colour", () => {
    expect(signalStrength("low_feed")).toMatchObject({ filled: 1, alert: false });
    expect(signalStrength("feed")).toMatchObject({ filled: 2, alert: false });
    expect(signalStrength("high_feed")).toMatchObject({ filled: 3, alert: false });
    expect(signalStrength("push")).toMatchObject({ filled: 3, alert: true });
  });

  it("never fills more strokes than the mark has", () => {
    for (const decision of Object.keys(DECISION_CONFIG)) {
      const { filled } = signalStrength(decision);
      expect(filled, decision).toBeGreaterThanOrEqual(0);
      expect(filled, decision).toBeLessThanOrEqual(SIGNAL_STROKES);
    }
  });

  it("only push is an alert, so the alert colour stays rare", () => {
    const alerts = Object.keys(DECISION_CONFIG).filter((d) => signalStrength(d).alert);
    expect(alerts).toEqual(["push"]);
  });

  it("shows nothing for hidden", () => {
    expect(signalStrength("hidden")).toMatchObject({ filled: 0, alert: false });
  });

  it("labels the mark in Hebrew with the shared decision label", () => {
    expect(signalStrength("high_feed").label).toBe(`עוצמת סיגנל: ${DECISION_CONFIG.high_feed.label}`);
    expect(signalStrength("push").label).toBe(`עוצמת סיגנל: ${DECISION_CONFIG.push.label}`);
  });

  it("treats an unknown decision like feed, as getDecisionConfig does", () => {
    expect(signalStrength("nonsense")).toEqual(signalStrength("feed"));
    expect(signalStrength(undefined)).toEqual(signalStrength("feed"));
  });
});
