import { describe, expect, it } from "vitest";
import { connectionErrorStrip, feedBodyState } from "./feedLoadModel";

describe("feedBodyState (journey audit D5)", () => {
  const base = { isBackendMode: true, isLoading: false, loadFailed: false, itemCount: 0 };

  it("a failed load with nothing to show is an error, never the 'nothing new' state", () => {
    expect(feedBodyState({ ...base, loadFailed: true })).toBe("error");
  });

  it("an empty successful load is the empty state", () => {
    expect(feedBodyState(base)).toBe("empty");
  });

  it("first load shows the skeleton; a reload over shown stories keeps them", () => {
    expect(feedBodyState({ ...base, isLoading: true })).toBe("loading");
    expect(feedBodyState({ ...base, isLoading: true, itemCount: 5 })).toBe("items");
    expect(feedBodyState({ ...base, loadFailed: true, itemCount: 5 })).toBe("items");
  });

  it("local (mock) mode never reports a load failure", () => {
    expect(feedBodyState({ ...base, isBackendMode: false, loadFailed: true })).toBe("empty");
  });
});

describe("connectionErrorStrip", () => {
  it("a reader sees Hebrew only: no raw server detail, no developer hint", () => {
    const strip = connectionErrorStrip({ area: "product", message: "GET /api/me/feed failed (500): boom" });
    expect(strip.message).not.toMatch(/[A-Za-z]/);
    expect(strip.title).not.toMatch(/[A-Za-z]/);
    expect(strip.hint).toBeNull();
  });

  it("the ops console keeps the detail and the developer hint", () => {
    const strip = connectionErrorStrip({ area: "ops", message: "GET /api/feed/guy failed (500): boom" });
    expect(strip.message).toContain("failed (500)");
    expect(strip.hint).toMatch(/uvicorn/);
  });
});
