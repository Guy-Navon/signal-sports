import { expect, it } from "vitest";
import { contrast } from "./contrastMath";

it("measures WCAG contrast ratios", () => {
  expect(contrast("#FFFFFF", "#000000")).toBeCloseTo(21, 5);
  expect(contrast("#777777", "#777777")).toBe(1);
  expect(contrast("#C8102E", "#1D42BA")).toBeCloseTo(1.40, 2);
});
