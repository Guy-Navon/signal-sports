import { describe, expect, it, vi } from "vitest";
import { recordArticleOpened } from "./usage";

describe("recordArticleOpened (#250)", () => {
  it("sends exactly one article_opened for the opened article", () => {
    const send = vi.fn(() => Promise.resolve());
    expect(recordArticleOpened("rss_1", { enabled: true, send })).toBe(true);
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith("rss_1", "article_opened");
  });

  it("sends nothing outside the reader's own session or without an id", () => {
    const send = vi.fn(() => Promise.resolve());
    expect(recordArticleOpened("rss_1", { enabled: false, send })).toBe(false);
    expect(recordArticleOpened(undefined, { enabled: true, send })).toBe(false);
    expect(send).not.toHaveBeenCalled();
  });

  it("never throws or rejects into navigation when the request fails", async () => {
    const rejecting = vi.fn(() => Promise.reject(new Error("offline")));
    const throwing = vi.fn(() => { throw new Error("boom"); });
    expect(() => recordArticleOpened("rss_1", { enabled: true, send: rejecting })).not.toThrow();
    expect(() => recordArticleOpened("rss_1", { enabled: true, send: throwing })).not.toThrow();
    await Promise.resolve();
  });
});
