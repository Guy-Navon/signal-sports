import { describe, it, expect } from "vitest";
import { PRODUCT_NAV_ITEMS } from "./navConfig";
import {
  consumerNavItems,
  consumerIconKey,
  nextBarShown,
  mastheadDate,
  accountInitial,
  accountMenuSections,
  pageSurface,
  SIGNAL_SURFACE_PATHS,
} from "./productShellModel";

const paths = (items) => items.map((item) => item.path);

describe("productShellModel", () => {
  describe("consumerNavItems", () => {
    it("orders the header as Part B §B6: feed, results, preferences, calibration", () => {
      expect(paths(consumerNavItems())).toEqual(["/", "/results", "/preferences", "/calibration"]);
    });

    it("keeps every product route and its label, so no destination is lost", () => {
      const items = consumerNavItems();
      expect(new Set(paths(items))).toEqual(new Set(paths(PRODUCT_NAV_ITEMS)));
      for (const original of PRODUCT_NAV_ITEMS) {
        expect(items.find((item) => item.path === original.path)?.label).toBe(original.label);
      }
    });

    it("stays data-driven: a destination added or removed in the list follows", () => {
      const merged = [
        { path: "/", label: "הפיד שלי" },
        { path: "/tune", label: "התאמה" },
        { path: "/results", label: "תוצאות" },
      ];
      expect(paths(consumerNavItems(/** @type {any} */ (merged)))).toEqual(["/", "/results", "/tune"]);
    });

    it("does not reorder the shared list the Ops rail renders", () => {
      const before = paths(PRODUCT_NAV_ITEMS);
      consumerNavItems();
      expect(paths(PRODUCT_NAV_ITEMS)).toEqual(before);
    });
  });

  describe("consumerIconKey", () => {
    it("gives each consumer destination its own icon in the new set", () => {
      expect(consumerNavItems().map((item) => consumerIconKey(item.path))).toEqual([
        "feed",
        "results",
        "preferences",
        "calibration",
      ]);
    });

    it("returns null for a destination without one, so the item's own icon is used", () => {
      expect(consumerIconKey("/tune")).toBeNull();
    });
  });

  describe("nextBarShown (collapse hysteresis)", () => {
    const tabsAbove = { ratio: 0, above: true };
    const partly = { ratio: 0.4, above: true };
    const tabsBack = { ratio: 1, above: false };

    it("starts hidden at the top of the page", () => {
      expect(nextBarShown(false, tabsBack)).toBe(false);
    });

    it("shows the slim bar only once the masthead tabs have fully left the top", () => {
      expect(nextBarShown(false, partly)).toBe(false);
      expect(nextBarShown(false, tabsAbove)).toBe(true);
    });

    it("keeps the bar while the tabs are only partly back (no flicker at the threshold)", () => {
      expect(nextBarShown(true, partly)).toBe(true);
      expect(nextBarShown(true, { ratio: 0.99, above: false })).toBe(true);
    });

    it("hides the bar once the tabs are fully visible again", () => {
      expect(nextBarShown(true, tabsBack)).toBe(false);
    });

    it("never shows the bar for tabs below the viewport (a short scroll from the top)", () => {
      expect(nextBarShown(false, { ratio: 0, above: false })).toBe(false);
    });

    it("keeps the bar while keyboard focus or an open menu is inside it", () => {
      expect(nextBarShown(true, { ...tabsBack, holding: true })).toBe(true);
      expect(nextBarShown(false, { ...tabsBack, holding: true })).toBe(false);
    });

    it("keeps the previous state when there is no measurement yet", () => {
      expect(nextBarShown(true, null)).toBe(true);
      expect(nextBarShown(false, undefined)).toBe(false);
    });
  });

  describe("mastheadDate", () => {
    it("writes the Hebrew weekday and date in Israel time, without the word 'יום'", () => {
      // 2026-11-14 10:00 UTC is Saturday in Jerusalem.
      expect(mastheadDate(new Date("2026-11-14T10:00:00Z"))).toBe("שבת, 14 בנובמבר 2026");
    });

    it("uses Asia/Jerusalem, not the device zone, around midnight", () => {
      // 22:30 UTC on Friday is already 00:30 on Saturday in Jerusalem (UTC+2).
      expect(mastheadDate(new Date("2026-11-13T22:30:00Z"))).toBe("שבת, 14 בנובמבר 2026");
    });

    it("names a weekday other than Saturday", () => {
      expect(mastheadDate(new Date("2026-11-16T10:00:00Z"))).toBe("שני, 16 בנובמבר 2026");
    });
  });

  describe("accountInitial", () => {
    it("takes the first letter of the email, upper-cased", () => {
      expect(accountInitial({ email: "guy@example.com" })).toBe("G");
    });

    it("returns null without a signed-in user, so an icon is drawn instead", () => {
      expect(accountInitial(null)).toBeNull();
      expect(accountInitial({ id: "u1" })).toBeNull();
      expect(accountInitial({ email: "  " })).toBeNull();
    });
  });

  describe("accountMenuSections", () => {
    it("a signed-in admin sees account, ground, admin and sign out, in that order", () => {
      expect(accountMenuSections({ signedIn: true, showConsoleEntry: true, showSwitcher: true }))
        .toEqual(["account", "ground", "admin", "signout"]);
    });

    it("a regular user never sees the admin section (#54)", () => {
      expect(accountMenuSections({ signedIn: true, showConsoleEntry: false, showSwitcher: false }))
        .toEqual(["account", "ground", "signout"]);
    });

    it("local mode keeps the ground switch and the admin tools, without account or sign out", () => {
      expect(accountMenuSections({ signedIn: false, showConsoleEntry: true, showSwitcher: true }))
        .toEqual(["ground", "admin"]);
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
      expect(pageSurface("/account")).toBe("signal");
      expect(pageSurface("/login")).toBe("orbit");
    });
  });
});
