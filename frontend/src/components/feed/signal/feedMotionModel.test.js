import { describe, expect, it } from "vitest";
import { QUEUE_PAGE_SIZE } from "@/components/feed/orbit/orbitQueueMotion";
import {
  ENTER_DURATION_MS,
  ENTER_MAX_STEPS,
  ENTER_STEP_MS,
  LOAD_SEQUENCE,
  enterDelayMs,
  enterStyle,
  loadSettleMs,
  nextArrivals,
  pageStaggerIndex,
  storyIdSet,
} from "./feedMotionModel";

describe("enterDelayMs: capped stagger (A5)", () => {
  it("steps per index from the section's base", () => {
    expect(enterDelayMs(0)).toBe(0);
    expect(enterDelayMs(1)).toBe(ENTER_STEP_MS);
    expect(enterDelayMs(2, 100)).toBe(100 + 2 * ENTER_STEP_MS);
  });

  it("never waits more than the cap, whatever the list length", () => {
    const cap = ENTER_MAX_STEPS * ENTER_STEP_MS;
    expect(enterDelayMs(ENTER_MAX_STEPS)).toBe(cap);
    expect(enterDelayMs(39)).toBe(cap);
    expect(enterDelayMs(198)).toBe(cap);
    expect(enterDelayMs(198, 50)).toBe(50 + cap);
  });

  it("treats a missing or bad index as the first", () => {
    expect(enterDelayMs(-3)).toBe(0);
    expect(enterDelayMs(Number.NaN)).toBe(0);
    expect(enterDelayMs(undefined, 40)).toBe(40);
  });

  it("is the cap the design system names: at most 6 steps", () => {
    expect(ENTER_MAX_STEPS).toBe(6);
  });
});

describe("pageStaggerIndex", () => {
  it("restarts the stagger on every page, so 'show more' rows do not all wait the cap", () => {
    expect(pageStaggerIndex(0)).toBe(0);
    expect(pageStaggerIndex(3)).toBe(3);
    expect(pageStaggerIndex(QUEUE_PAGE_SIZE)).toBe(0);
    expect(pageStaggerIndex(QUEUE_PAGE_SIZE + 2)).toBe(2);
  });
});

describe("enterStyle", () => {
  it("hands the delay to CSS as a custom property", () => {
    expect(enterStyle(2, 100)).toEqual({ "--sg-enter-delay": `${100 + 2 * ENTER_STEP_MS}ms` });
    expect(enterStyle(500)).toEqual({ "--sg-enter-delay": `${ENTER_MAX_STEPS * ENTER_STEP_MS}ms` });
  });
});

describe("loadSettleMs", () => {
  it("is constant for any feed size and stays under a second", () => {
    const latest = Math.max(...Object.values(LOAD_SEQUENCE));
    expect(loadSettleMs()).toBe(latest + ENTER_MAX_STEPS * ENTER_STEP_MS + ENTER_DURATION_MS);
    expect(loadSettleMs()).toBeLessThan(1000);
  });

  it("orders the page top to bottom: head, pills, lead, important, results, stream, side", () => {
    const order = ["head", "pills", "lead", "important", "results", "stream", "side"];
    const values = order.map((key) => LOAD_SEQUENCE[key]);
    expect(values.every((value) => Number.isFinite(value))).toBe(true);
    expect([...values].sort((a, b) => a - b)).toEqual(values);
  });
});

describe("storyIdSet", () => {
  it("collects cluster and article ids, skipping stories with none", () => {
    const set = storyIdSet([{ clusterId: "c1", id: "a1" }, { id: "a2" }, {}]);
    expect([...set]).toEqual(["c1", "a2"]);
  });
});

describe("nextArrivals: which stories are new after a refresh", () => {
  const ids = (...values) => new Set(values);

  it("announces nothing on the first load: everything is new, so nothing is", () => {
    expect(nextArrivals({ previousIds: null, currentIds: ids("a", "b"), previousArrivals: ids() }).size).toBe(0);
    expect(nextArrivals({ previousIds: ids(), currentIds: ids("a", "b"), previousArrivals: ids() }).size).toBe(0);
  });

  it("marks the stories that were not there before", () => {
    const arrivals = nextArrivals({
      previousIds: ids("a", "b", "c", "d"),
      currentIds: ids("x", "a", "b", "c", "d"),
      previousArrivals: ids(),
    });
    expect([...arrivals]).toEqual(["x"]);
  });

  it("keeps the earlier arrivals when a refresh brings nothing new", () => {
    const arrivals = nextArrivals({
      previousIds: ids("x", "a", "b", "c"),
      currentIds: ids("x", "a", "b", "c"),
      previousArrivals: ids("x"),
    });
    expect([...arrivals]).toEqual(["x"]);
  });

  it("drops earlier arrivals that left the feed", () => {
    const arrivals = nextArrivals({
      previousIds: ids("x", "a", "b", "c"),
      currentIds: ids("a", "b", "c"),
      previousArrivals: ids("x"),
    });
    expect(arrivals.size).toBe(0);
  });

  it("a newer refresh replaces the older arrivals", () => {
    const arrivals = nextArrivals({
      previousIds: ids("x", "a", "b", "c"),
      currentIds: ids("y", "x", "a", "b", "c"),
      previousArrivals: ids("x"),
    });
    expect([...arrivals]).toEqual(["y"]);
  });

  it("treats a mostly new list as a different feed, not arrivals (a re-score, another profile)", () => {
    const arrivals = nextArrivals({
      previousIds: ids("a", "b", "c", "d"),
      currentIds: ids("p", "q", "r", "a"),
      previousArrivals: ids(),
    });
    expect(arrivals.size).toBe(0);
  });
});
