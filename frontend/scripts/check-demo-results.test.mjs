import { expect, it } from "vitest";
import { checkBundleMarkers } from "./check-demo-bundle.mjs";

const bundle = text => [{ name: "fixture.js", text }];
it("permits static result statistics, game popups and chosen-player lines in the demo", () => {
  const result = checkBundleMarkers(bundle('"private-results-statistics"; "סגירת פרטי המשחק"; "השחקנים שלך"'), []);
  expect(result.filter(problem => problem.includes("FORBIDDEN"))).toEqual([]);
});
it.each(['/api/me/results', 'credentials:"include"', 'method:"POST"', 'method:"DELETE"', '"within AuthProvider"'])(
  "still rejects APIs, authenticated requests and write paths (%s)", marker => {
    expect(checkBundleMarkers(bundle(marker), []).some(problem => problem.includes("FORBIDDEN"))).toBe(true);
  });
it("still calibrates forbidden markers against the application bundle", () => {
  expect(checkBundleMarkers([], []).some(problem => problem.includes("STALE") && problem.includes("API client"))).toBe(true);
});
