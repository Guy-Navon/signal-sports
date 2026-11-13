import { describe, it, expect } from "vitest";
import { PRODUCT_NAV_ITEMS } from "./navConfig";
import {
  consumerNavItems,
  consumerDockItems,
  pageSurface,
  SIGNAL_SURFACE_PATHS,
} from "./productShellModel";

const paths = (items) => items.map((item) => item.path);

describe("productShellModel", () => {
  describe("consumerNavItems", () => {
    it("orders the top bar as Part B §B6: feed, results, preferences, calibration", () => {
      expect(paths(consumerNavItems())).toEqual(["/", "/results", "/preferences", "/calibration"]);
    });

    it("keeps every product route and its label, so no destination is lost", () => {
      const items = consumerNavItems();
      expect(new Set(paths(items))).toEqual(new Set(paths(PRODUCT_NAV_ITEMS)));
      for (const original of PRODUCT_NAV_ITEMS) {
        expect(items.find((item) => item.path === original.path)?.label).toBe(original.label);
      }
    });

    it("does not reorder the shared list the Ops rail renders", () => {
      const before = paths(PRODUCT_NAV_ITEMS);
      consumerNavItems();
      expect(paths(PRODUCT_NAV_ITEMS)).toEqual(before);
    });
  });

  describe("consumerDockItems", () => {
    it("adds the console entry last when the visitor may enter it", () => {
      expect(paths(consumerDockItems({ isBackendMode: false, showConsoleEntry: true }))).toEqual([
        "/",
        "/results",
        "/preferences",
        "/calibration",
        "/sources",
      ]);
    });

    it("drops the console entry for a visitor who may not enter it (#54)", () => {
      expect(paths(consumerDockItems({ isBackendMode: true, showConsoleEntry: false }))).toEqual([
        "/",
        "/results",
        "/preferences",
        "/calibration",
      ]);
    });
  });

  describe("pageSurface", () => {
    it("keeps unmigrated consumer pages on the Orbit scope", () => {
      for (const path of ["/", "/preferences", "/interests", "/calibration", "/results", "/account"]) {
        expect(pageSurface(path, [])).toBe("orbit");
      }
    });

    it("gives a migrated page the Signal UI scope", () => {
      expect(pageSurface("/", ["/"])).toBe("signal");
      expect(pageSurface("/results", ["/"])).toBe("orbit");
    });

    it("defaults to the shipped migration list", () => {
      for (const path of SIGNAL_SURFACE_PATHS) {
        expect(pageSurface(path)).toBe("signal");
      }
      expect(pageSurface("/account")).toBe("orbit");
    });
  });
});
