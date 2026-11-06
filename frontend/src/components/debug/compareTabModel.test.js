import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { COMPARE_DEMO_ONLY_MESSAGE, showsDemoComparison } from "./compareTabModel";

describe("Debug's compare tab (#199)", () => {
  it("shows the demo table only in local mode", () => {
    expect(showsDemoComparison(false)).toBe(true);
    expect(showsDemoComparison(true)).toBe(false);
  });

  it("backend mode has a one-line Hebrew message", () => {
    expect(COMPARE_DEMO_ONLY_MESSAGE).toMatch(/[֐-׿]/);
    expect(COMPARE_DEMO_ONLY_MESSAGE).not.toContain("\n");
  });

  it("Debug can reach the demo only through a lazy import", () => {
    const source = readFileSync(new URL("../../pages/Debug.jsx", import.meta.url), "utf8");
    expect(source).toContain('lazy(() => import("@/components/debug/DemoProfileComparison"))');
    expect(source).not.toMatch(/^import .*(DemoProfileComparison|localDemo|mockArticles|relevanceEngine)/m);
  });
});
