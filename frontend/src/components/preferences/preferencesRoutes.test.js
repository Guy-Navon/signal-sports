import { describe, expect, it } from "vitest";
import { PREFERENCE_TABS, legacyPreferencesTarget, preferenceTab, adjacentTab } from "./preferencesRoutes";

describe("preferences URLs", () => {
  it("gives each tab a stable, distinct link", () => {
    expect(PREFERENCE_TABS.map(({ path }) => path)).toEqual([
      "/preferences", "/preferences/calibration", "/preferences/learned", "/preferences/muted",
    ]);
    for (const tab of PREFERENCE_TABS) expect(preferenceTab(tab.path)).toBe(tab.id);
    expect(preferenceTab("/preferences/")).toBe("following");
    expect(preferenceTab("/preferences/unknown")).toBeNull();
  });

  it.each([
    ["/calibration", "/preferences/calibration"],
    ["/interests", "/preferences"],
  ])("preserves the complete query and anchor from %s", (old, target) => {
    const search = "?from=email&tag=a%2Fb&tag=c+v&empty=";
    expect(legacyPreferencesTarget(old, search, "#cal-item-a")).toBe(`${target}${search}#cal-item-a`);
    expect(legacyPreferencesTarget(old)).toBe(target);
  });
});

describe("RTL tab keyboard navigation", () => {
  const ids = PREFERENCE_TABS.map(({ id }) => id);
  it("moves arrows in visual RTL order, wraps, and supports Home/End", () => {
    expect(adjacentTab("following", "ArrowLeft")).toBe("calibration");
    expect(adjacentTab("following", "ArrowRight")).toBe("muted");
    expect(adjacentTab("muted", "ArrowLeft")).toBe("following");
    for (const id of ids) {
      expect(adjacentTab(id, "Home")).toBe("following");
      expect(adjacentTab(id, "End")).toBe("muted");
      expect(adjacentTab(id, "Tab")).toBeNull();
      expect(adjacentTab(id, "Enter")).toBeNull();
    }
  });
});
