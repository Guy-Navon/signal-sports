import { expect, it } from "vitest";
import { checkBundleMarkers } from "./check-demo-bundle.mjs";

const bundle = (text) => [{ name: "fixture.js", text }];
it("rejects results-stat rendering in the public demo even without API or write imports", () => {
  const result = checkBundleMarkers(bundle('element.dataset.scope = "private-results-statistics"'), bundle('"private-results-statistics"'));
  expect(result.some(problem => problem.includes("FORBIDDEN") && problem.includes("results statistics"))).toBe(true);
});
it("requires the results-stat marker in the main bundle so a renamed marker cannot silently weaken the guard", () => {
  const result = checkBundleMarkers(bundle('"scores only"'), bundle('"other UI"'));
  expect(result.some(problem => problem.includes("STALE") && problem.includes("results statistics"))).toBe(true);
});
it("permits a scores-only demo when the stats marker stays in the application", () => {
  const result = checkBundleMarkers(bundle('home:{score:87},away:{score:105}'), bundle('"private-results-statistics"'));
  expect(result.some(problem => problem.includes("results statistics"))).toBe(false);
});
