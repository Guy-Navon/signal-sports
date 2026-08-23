import { describe, expect, it } from "vitest";
import {
  FIELD_SCROLL_MAX_WIDTH,
  FOCUS_TARGETS,
  focusIntentForCollapse,
  focusIntentForExpand,
  focusIntentForStorySelection,
  isFieldExpanded,
  resolveStoryChange,
  SCROLL_POLICY,
  shouldScrollFieldIntoView,
  shouldScrollForIntent,
} from "./orbitFocusModel";

describe("shouldScrollFieldIntoView", () => {
  it("scrolls below the desktop breakpoint, where the field is stacked", () => {
    expect(shouldScrollFieldIntoView(320)).toBe(true);
    expect(shouldScrollFieldIntoView(390)).toBe(true);
    expect(shouldScrollFieldIntoView(FIELD_SCROLL_MAX_WIDTH - 1)).toBe(true);
  });

  it("leaves the sticky desktop field alone", () => {
    expect(shouldScrollFieldIntoView(FIELD_SCROLL_MAX_WIDTH)).toBe(false);
    expect(shouldScrollFieldIntoView(1440)).toBe(false);
  });

  it("does not scroll when the width is unknown", () => {
    expect(shouldScrollFieldIntoView(undefined)).toBe(false);
    expect(shouldScrollFieldIntoView(Number.NaN)).toBe(false);
  });
});

describe("shouldScrollForIntent", () => {
  it("always scrolls for expansion, at any width", () => {
    expect(shouldScrollForIntent(SCROLL_POLICY.always, 1440)).toBe(true);
    expect(shouldScrollForIntent(SCROLL_POLICY.always, 320)).toBe(true);
  });

  it("scrolls only on stacked layouts for story selection", () => {
    expect(shouldScrollForIntent(SCROLL_POLICY.ifNarrow, 390)).toBe(true);
    expect(shouldScrollForIntent(SCROLL_POLICY.ifNarrow, 1440)).toBe(false);
  });

  it("never scrolls when the reader did not ask for it", () => {
    expect(shouldScrollForIntent(SCROLL_POLICY.never, 320)).toBe(false);
    expect(shouldScrollForIntent(SCROLL_POLICY.never, 1440)).toBe(false);
  });

  it("treats an unknown policy as no scroll", () => {
    expect(shouldScrollForIntent(undefined, 320)).toBe(false);
    expect(shouldScrollForIntent("sideways", 320)).toBe(false);
  });
});

describe("focus intents", () => {
  it("moves focus into the core when a queue story is chosen", () => {
    expect(focusIntentForStorySelection()).toEqual({
      target: FOCUS_TARGETS.core,
      collapse: true,
      scrollField: SCROLL_POLICY.ifNarrow,
    });
  });

  it("moves focus to the close control when the cluster opens", () => {
    expect(focusIntentForExpand()).toEqual({
      target: FOCUS_TARGETS.closeAction,
      scrollField: SCROLL_POLICY.always,
    });
  });

  it("returns focus to the control that opened it when the cluster closes", () => {
    expect(focusIntentForCollapse()).toEqual({
      target: FOCUS_TARGETS.primaryAction,
      scrollField: SCROLL_POLICY.never,
    });
  });

  it("never returns a target outside the known roles", () => {
    const roles = Object.values(FOCUS_TARGETS);
    for (const intent of [
      focusIntentForStorySelection(),
      focusIntentForExpand(),
      focusIntentForCollapse(),
    ]) {
      expect(roles).toContain(intent.target);
    }
  });
});

describe("resolveStoryChange", () => {
  it("does nothing on first render", () => {
    expect(
      resolveStoryChange({ previousStoryId: null, nextStoryId: "a", expandedStoryId: null })
    ).toEqual({ collapse: false, target: null, scrollField: SCROLL_POLICY.never });
  });

  it("does nothing when the focused story is unchanged", () => {
    expect(
      resolveStoryChange({ previousStoryId: "a", nextStoryId: "a", expandedStoryId: "a" })
    ).toEqual({ collapse: false, target: null, scrollField: SCROLL_POLICY.never });
  });

  // An expanded field showing a story that is no longer focused is incoherent.
  it("collapses when the focused story is replaced while expanded", () => {
    expect(
      resolveStoryChange({ previousStoryId: "a", nextStoryId: "b", expandedStoryId: "a" })
    ).toEqual({ collapse: true, target: FOCUS_TARGETS.core, scrollField: SCROLL_POLICY.never });
  });

  it("collapses a stale expansion without stealing focus", () => {
    // "c" was expanded, but the reader's focus was never inside it.
    expect(
      resolveStoryChange({ previousStoryId: "a", nextStoryId: "b", expandedStoryId: "c" })
    ).toEqual({ collapse: true, target: null, scrollField: SCROLL_POLICY.never });
  });

  it("leaves focus alone when nothing was expanded", () => {
    expect(
      resolveStoryChange({ previousStoryId: "a", nextStoryId: "b", expandedStoryId: null })
    ).toEqual({ collapse: false, target: null, scrollField: SCROLL_POLICY.never });
  });

  it("handles the focused story disappearing entirely", () => {
    expect(
      resolveStoryChange({ previousStoryId: "a", nextStoryId: null, expandedStoryId: "a" })
    ).toEqual({ collapse: true, target: FOCUS_TARGETS.core, scrollField: SCROLL_POLICY.never });
  });
});

describe("isFieldExpanded", () => {
  it("is expanded only when the remembered id matches the live story", () => {
    expect(isFieldExpanded("a", "a")).toBe(true);
    expect(isFieldExpanded("a", "b")).toBe(false);
  });

  it("is never expanded without an active story", () => {
    expect(isFieldExpanded(null, null)).toBe(false);
    expect(isFieldExpanded(undefined, "a")).toBe(false);
    expect(isFieldExpanded(null, "a")).toBe(false);
  });
});
