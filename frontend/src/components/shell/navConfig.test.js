import { describe, it, expect } from "vitest";
import {
  PRODUCT_NAV_ITEMS,
  OPS_NAV_ITEMS,
  OPS_PATHS,
  getOpsNavItems,
  getAreaForPath,
  getMobileNavItems,
} from "./navConfig";

describe("navConfig", () => {
  describe("nav item lists", () => {
    it("keeps all product routes", () => {
      expect(PRODUCT_NAV_ITEMS.map((i) => i.path)).toEqual([
        "/",
        "/preferences",
        "/calibration",
        "/results",
      ]);
    });

    it("keeps all ops routes", () => {
      expect(OPS_NAV_ITEMS.map((i) => i.path)).toEqual(["/sources", "/debug", "/llm-qa"]);
    });

    it("every item has a Hebrew-first label and an icon", () => {
      for (const item of [...PRODUCT_NAV_ITEMS, ...OPS_NAV_ITEMS]) {
        expect(item.label.length).toBeGreaterThan(0);
        expect(item.icon).toBeTruthy();
      }
    });
  });

  describe("getOpsNavItems", () => {
    it("includes llm-qa only in backend mode", () => {
      expect(getOpsNavItems(true).map((i) => i.path)).toContain("/llm-qa");
      expect(getOpsNavItems(false).map((i) => i.path)).not.toContain("/llm-qa");
    });

    it("always includes sources and debug", () => {
      for (const isBackendMode of [true, false]) {
        const paths = getOpsNavItems(isBackendMode).map((i) => i.path);
        expect(paths).toContain("/sources");
        expect(paths).toContain("/debug");
      }
    });
  });

  describe("getAreaForPath", () => {
    it.each([
      ["/", "product"],
      ["/preferences", "product"],
      ["/calibration", "product"],
      ["/results", "product"],
      ["/sources", "ops"],
      ["/debug", "ops"],
      ["/llm-qa", "ops"],
    ])("resolves %s to %s", (path, area) => {
      expect(getAreaForPath(path)).toBe(area);
    });

    it("treats unknown paths as product", () => {
      expect(getAreaForPath("/nope")).toBe("product");
    });

    it("stays in sync with OPS_PATHS", () => {
      for (const path of OPS_PATHS) {
        expect(getAreaForPath(path)).toBe("ops");
      }
    });
  });

  describe("getMobileNavItems", () => {
    it("product area shows product items plus a console entry", () => {
      const paths = getMobileNavItems("product", false).map((i) => i.path);
      expect(paths).toEqual(["/", "/preferences", "/calibration", "/results", "/sources"]);
    });

    it("ops area shows ops items plus a back-to-feed entry", () => {
      const paths = getMobileNavItems("ops", true).map((i) => i.path);
      expect(paths).toEqual(["/sources", "/debug", "/llm-qa", "/"]);
    });

    it("ops area respects the llm-qa backend gate", () => {
      const paths = getMobileNavItems("ops", false).map((i) => i.path);
      expect(paths).toEqual(["/sources", "/debug", "/"]);
    });
  });
});
