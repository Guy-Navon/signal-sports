import { describe, expect, it } from "vitest";
import {
  QUEUE_ENTER_DURATION_S,
  QUEUE_PAGE_SIZE,
  QUEUE_REDUCED_DURATION_S,
  QUEUE_STAGGER_MAX_STEPS,
  QUEUE_STAGGER_STEP_S,
  queueEnterDelay,
  queueEnterMotion,
  queueEnterTransition,
  queuePage,
  queueSettleSeconds,
} from "./orbitQueueMotion";

describe("queueEnterDelay", () => {
  it("does not delay the first card", () => {
    expect(queueEnterDelay(0)).toBe(0);
  });

  it("staggers early cards", () => {
    expect(queueEnterDelay(1)).toBeCloseTo(QUEUE_STAGGER_STEP_S, 6);
    expect(queueEnterDelay(3)).toBeCloseTo(3 * QUEUE_STAGGER_STEP_S, 6);
  });

  it("never exceeds the stagger cap, however long the list", () => {
    const cap = QUEUE_STAGGER_MAX_STEPS * QUEUE_STAGGER_STEP_S;
    for (const index of [QUEUE_STAGGER_MAX_STEPS, 50, 197, 5000]) {
      expect(queueEnterDelay(index)).toBeCloseTo(cap, 6);
    }
  });

  it("is monotonic and never negative", () => {
    let previous = -1;
    for (let i = 0; i < 250; i += 1) {
      const delay = queueEnterDelay(i);
      expect(delay).toBeGreaterThanOrEqual(previous);
      expect(delay).toBeGreaterThanOrEqual(0);
      previous = delay;
    }
  });

  it("removes the stagger entirely under reduced motion", () => {
    for (const index of [0, 5, 197]) expect(queueEnterDelay(index, true)).toBe(0);
  });

  it("tolerates junk input", () => {
    expect(queueEnterDelay(undefined)).toBe(0);
    expect(queueEnterDelay(Number.NaN)).toBe(0);
    expect(queueEnterDelay(-4)).toBe(0);
  });
});

describe("queueSettleSeconds", () => {
  // The regression this whole module exists for: settle time must not scale
  // with card count. Card 196 used to start 4.9s after a filter click.
  it("is constant once past the stagger cap", () => {
    const at50 = queueSettleSeconds(50);
    for (const count of [100, 198, 1000, 10000]) {
      expect(queueSettleSeconds(count)).toBeCloseTo(at50, 6);
    }
  });

  it("stays well under a second for any list size", () => {
    for (const count of [1, 20, 198, 10000]) {
      expect(queueSettleSeconds(count)).toBeLessThan(0.5);
    }
  });

  it("does not grow linearly — 198 cards cost less than twice 10 cards", () => {
    expect(queueSettleSeconds(198)).toBeLessThan(queueSettleSeconds(10) * 2);
  });

  it("is shorter under reduced motion", () => {
    expect(queueSettleSeconds(198, true)).toBe(QUEUE_REDUCED_DURATION_S);
    expect(queueSettleSeconds(198, true)).toBeLessThan(queueSettleSeconds(198));
  });

  it("is zero for an empty list", () => {
    expect(queueSettleSeconds(0)).toBe(0);
  });
});

describe("queueEnterTransition", () => {
  it("carries the capped delay and the right duration", () => {
    expect(queueEnterTransition(500)).toMatchObject({
      duration: QUEUE_ENTER_DURATION_S,
      delay: QUEUE_STAGGER_MAX_STEPS * QUEUE_STAGGER_STEP_S,
    });
    expect(queueEnterTransition(500, true)).toMatchObject({
      duration: QUEUE_REDUCED_DURATION_S,
      delay: 0,
    });
  });
});

describe("queueEnterMotion", () => {
  it("drops the vertical offset under reduced motion", () => {
    expect(queueEnterMotion(false).initial).toHaveProperty("y");
    expect(queueEnterMotion(true).initial).not.toHaveProperty("y");
  });
});

describe("queuePage", () => {
  it("caps the rendered node count", () => {
    expect(queuePage(198)).toEqual({
      visible: QUEUE_PAGE_SIZE,
      remaining: 198 - QUEUE_PAGE_SIZE,
      hasMore: true,
    });
  });

  it("shows everything when the list is short", () => {
    expect(queuePage(12)).toEqual({ visible: 12, remaining: 0, hasMore: false });
  });

  it("grows a page at a time", () => {
    expect(queuePage(198, 2).visible).toBe(QUEUE_PAGE_SIZE * 2);
    expect(queuePage(198, 99)).toEqual({ visible: 198, remaining: 0, hasMore: false });
  });

  it("handles an empty queue", () => {
    expect(queuePage(0)).toEqual({ visible: 0, remaining: 0, hasMore: false });
  });
});
