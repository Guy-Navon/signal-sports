import { describe, expect, it } from "vitest";
import { affinitySignal } from "./affinitySignal";

describe("preference-level signal presentation", () => {
  it("uses the shared decision marks in ascending interest order", () => {
    expect([-1, 0, 1, 2].map(affinitySignal)).toEqual(["low_feed", "feed", "high_feed", "push"]);
  });

  it("does not invent a visible decision for a muted or unknown level", () => {
    for (const level of [-2, -3, 3, null, undefined, NaN]) {
      expect(affinitySignal(level)).toBeNull();
    }
  });
});
