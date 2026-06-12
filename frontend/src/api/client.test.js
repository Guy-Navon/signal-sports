import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  getHealth, getFeed, getDebugFeed, getProfiles, submitFeedback, getCalibrationHeadlines,
  getIngestSources, runIngestion, getIngestRuns, getIngestQuality,
} from "./client";

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

// ── Ingestion sources ─────────────────────────────────────────────────────────

describe("getIngestSources", () => {
  it("calls /api/ingest/sources and returns array", async () => {
    const payload = [
      { source_id: "walla_sport", display_name: "וואלה ספורט", language: "he", enabled: true },
      { source_id: "eurohoops", display_name: "Eurohoops", language: "en", enabled: true },
    ];
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await getIngestSources();

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/ingest/sources");
    expect(result).toEqual(payload);
  });

  it("throws a descriptive error on server failure", async () => {
    vi.stubGlobal("fetch", mockFetchHttpError(500, "Internal Server Error"));

    await expect(getIngestSources()).rejects.toThrow("500");
  });
});

// ── Run ingestion ─────────────────────────────────────────────────────────────

describe("runIngestion", () => {
  it("calls POST /api/ingest/run when no sourceId given", async () => {
    const payload = { status: "ok", sources: [{ source_id: "eurohoops", fetched: 10, inserted: 5, skipped_duplicate: 5, skipped_filtered: 0, failed: 0 }] };
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await runIngestion();

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/ingest/run");
    expect(url).not.toContain("source_id");
    expect(options.method).toBe("POST");
    expect(result).toEqual(payload);
  });

  it("calls POST /api/ingest/run?source_id=walla_sport when sourceId given", async () => {
    const payload = { status: "ok", sources: [{ source_id: "walla_sport", fetched: 30, inserted: 30, skipped_duplicate: 0, skipped_filtered: 0, failed: 0 }] };
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    await runIngestion("walla_sport");

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/ingest/run");
    expect(url).toContain("source_id=walla_sport");
    expect(options.method).toBe("POST");
  });

  it("throws a descriptive error on network failure", async () => {
    vi.stubGlobal("fetch", mockFetchNetworkError("Failed to fetch"));

    await expect(runIngestion()).rejects.toThrow("Cannot reach backend");
  });
});

// ── Ingestion runs ────────────────────────────────────────────────────────────

describe("getIngestRuns", () => {
  it("calls /api/ingest/runs with default limit", async () => {
    const payload = [{ id: "run-1", source_id: "walla_sport", status: "ok", fetched_count: 30, inserted_count: 30 }];
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await getIngestRuns();

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/ingest/runs");
    expect(url).toContain("limit=5");
    expect(result).toEqual(payload);
  });

  it("calls /api/ingest/runs with custom limit", async () => {
    const mockFetch = mockFetchSuccess([]);
    vi.stubGlobal("fetch", mockFetch);

    await getIngestRuns(10);

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("limit=10");
  });
});

// ── Ingestion quality ─────────────────────────────────────────────────────────

describe("getIngestQuality", () => {
  it("calls /api/ingest/quality and returns data", async () => {
    const payload = {
      total_rss_articles: 60,
      sport_breakdown: { basketball: 33, unknown: 22, football: 5 },
      league_breakdown: {},
      event_type_breakdown: { news: 51, finals_result: 4 },
      importance_breakdown: { medium: 34, low: 22, very_high: 4 },
      low_confidence_count: 18,
      questionable_articles: [],
    };
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await getIngestQuality();

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/ingest/quality");
    expect(result.total_rss_articles).toBe(60);
    expect(result.sport_breakdown.basketball).toBe(33);
    expect(result.questionable_articles).toEqual([]);
  });

  it("throws a descriptive error when backend returns error", async () => {
    vi.stubGlobal("fetch", mockFetchHttpError(503, "Service unavailable"));

    await expect(getIngestQuality()).rejects.toThrow("503");
  });
});
