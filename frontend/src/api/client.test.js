import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { getHealth, getFeed, getDebugFeed, getProfiles, submitFeedback, getCalibrationHeadlines } from "./client";

// ── Helpers ───────────────────────────────────────────────────────────────────

function mockFetchSuccess(data) {
  return vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(data),
  });
}

function mockFetchHttpError(status, detail) {
  return vi.fn().mockResolvedValue({
    ok: false,
    status,
    json: () => Promise.resolve({ detail }),
    text: () => Promise.resolve(detail),
  });
}

function mockFetchNetworkError(message) {
  return vi.fn().mockRejectedValue(new Error(message));
}

beforeEach(() => {
  vi.stubGlobal("fetch", undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ── Health check ──────────────────────────────────────────────────────────────

describe("getHealth", () => {
  it("returns parsed JSON on success", async () => {
    vi.stubGlobal("fetch", mockFetchSuccess({ status: "ok" }));
    const result = await getHealth();
    expect(result).toEqual({ status: "ok" });
  });
});

// ── Feed fetching ─────────────────────────────────────────────────────────────

describe("getFeed", () => {
  it("calls /api/feed/{userId} and returns array", async () => {
    const payload = [{ article: { id: "article_001" }, decision: "push" }];
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await getFeed("guy");

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/feed/guy");
    expect(result).toEqual(payload);
  });

  it("throws a descriptive error when backend returns 404", async () => {
    vi.stubGlobal("fetch", mockFetchHttpError(404, "Profile 'unknown' not found"));

    await expect(getFeed("unknown")).rejects.toThrow("404");
    await expect(getFeed("unknown")).rejects.toThrow("Profile 'unknown' not found");
  });

  it("throws a descriptive error on network failure", async () => {
    vi.stubGlobal("fetch", mockFetchNetworkError("Failed to fetch"));

    await expect(getFeed("guy")).rejects.toThrow("Cannot reach backend");
  });
});

// ── Debug feed ────────────────────────────────────────────────────────────────

describe("getDebugFeed", () => {
  it("calls /api/debug/feed/{userId}", async () => {
    const mockFetch = mockFetchSuccess([]);
    vi.stubGlobal("fetch", mockFetch);

    await getDebugFeed("guy");

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/debug/feed/guy");
  });
});

// ── Profiles ──────────────────────────────────────────────────────────────────

describe("getProfiles", () => {
  it("calls /api/profiles and returns array", async () => {
    const payload = [{ user_id: "guy", display_name: "Guy" }];
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await getProfiles();

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/profiles");
    expect(result).toEqual(payload);
  });
});

// ── Feedback POST ─────────────────────────────────────────────────────────────

describe("submitFeedback", () => {
  it("sends POST with correct JSON body", async () => {
    const responsePayload = {
      id: "uuid-123",
      user_id: "guy",
      article_id: "article_001",
      action: "more_like_this",
      created_at: "2026-06-11T08:00:00Z",
    };
    const mockFetch = mockFetchSuccess(responsePayload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await submitFeedback({
      user_id: "guy",
      article_id: "article_001",
      action: "more_like_this",
    });

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/feedback");
    expect(options.method).toBe("POST");
    expect(options.headers["Content-Type"]).toBe("application/json");

    const body = JSON.parse(options.body);
    expect(body.user_id).toBe("guy");
    expect(body.article_id).toBe("article_001");
    expect(body.action).toBe("more_like_this");

    expect(result).toEqual(responsePayload);
  });

  it("throws a descriptive error when action is invalid (422)", async () => {
    vi.stubGlobal("fetch", mockFetchHttpError(422, "Invalid action 'bad_action'"));

    await expect(
      submitFeedback({ user_id: "guy", article_id: "article_001", action: "bad_action" })
    ).rejects.toThrow("422");
  });
});

// ── Calibration headlines ─────────────────────────────────────────────────────

describe("getCalibrationHeadlines", () => {
  it("calls /api/calibration/headlines", async () => {
    const payload = [{ id: "h1", title: "Test", sport: "basketball", event_type: "signing", importance: "high" }];
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await getCalibrationHeadlines();

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/calibration/headlines");
    expect(result).toEqual(payload);
  });
});
