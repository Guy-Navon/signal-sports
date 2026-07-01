import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  getHealth, getFeed, getDebugFeed, getProfiles, submitFeedback, getCalibrationHeadlines,
  getIngestSources, runIngestion, getIngestRuns, getIngestQuality,
  getClassifyStatus, classifyBackfill, resetRssData,
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

// ── getClassifyStatus ─────────────────────────────────────────────────────────

describe("getClassifyStatus", () => {
  it("calls GET /api/classify/status and returns status object", async () => {
    const payload = {
      provider: "ollama",
      can_classify: true,
      hebrew_broad_sources: ["walla_sport", "israel_hayom_sport"],
      model: "llama3.2:3b",
      base_url: "http://localhost:11434",
      reset_allowed: false,
    };
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await getClassifyStatus();

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/classify/status");
    expect(options?.method).toBeUndefined(); // GET
    expect(result).toEqual(payload);
  });

  it("includes reset_allowed field in response", async () => {
    const payload = {
      provider: "disabled",
      can_classify: false,
      hebrew_broad_sources: [],
      model: null,
      base_url: null,
      reset_allowed: true,
    };
    vi.stubGlobal("fetch", mockFetchSuccess(payload));

    const result = await getClassifyStatus();
    expect(result.reset_allowed).toBe(true);
    expect(result.can_classify).toBe(false);
  });

  it("throws a descriptive error on network failure", async () => {
    vi.stubGlobal("fetch", mockFetchNetworkError("Connection refused"));

    await expect(getClassifyStatus()).rejects.toThrow("Cannot reach backend");
  });
});

// ── classifyBackfill ──────────────────────────────────────────────────────────

describe("classifyBackfill", () => {
  const backfillResponse = {
    provider: "ollama:llama3.2:3b",
    processed: 18,
    llm_classified: 12,
    guardrail_corrections: 3,
    fallback_count: 2,
    low_confidence_count: 1,
    skipped_already_classified: 10,
    skipped_provider_not_ready: 0,
    dry_run: false,
  };

  it("calls POST /api/classify/backfill with no params when called with no args", async () => {
    const mockFetch = mockFetchSuccess(backfillResponse);
    vi.stubGlobal("fetch", mockFetch);

    await classifyBackfill();

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/classify/backfill");
    expect(url).not.toContain("?");
    expect(options.method).toBe("POST");
  });

  it("adds source_id query param when provided", async () => {
    const mockFetch = mockFetchSuccess(backfillResponse);
    vi.stubGlobal("fetch", mockFetch);

    await classifyBackfill({ sourceId: "walla_sport" });

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("source_id=walla_sport");
  });

  it("adds dry_run=true when dryRun is true", async () => {
    const mockFetch = mockFetchSuccess(backfillResponse);
    vi.stubGlobal("fetch", mockFetch);

    await classifyBackfill({ dryRun: true });

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("dry_run=true");
  });

  it("adds force=true when force is true", async () => {
    const mockFetch = mockFetchSuccess(backfillResponse);
    vi.stubGlobal("fetch", mockFetch);

    await classifyBackfill({ force: true });

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("force=true");
  });

  it("does not include dry_run or force when they are false (default)", async () => {
    const mockFetch = mockFetchSuccess(backfillResponse);
    vi.stubGlobal("fetch", mockFetch);

    await classifyBackfill({ sourceId: "walla_sport" });

    const [url] = mockFetch.mock.calls[0];
    expect(url).not.toContain("dry_run");
    expect(url).not.toContain("force");
  });

  it("combines multiple params correctly", async () => {
    const mockFetch = mockFetchSuccess(backfillResponse);
    vi.stubGlobal("fetch", mockFetch);

    await classifyBackfill({ sourceId: "walla_sport", dryRun: true, force: true });

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("source_id=walla_sport");
    expect(url).toContain("dry_run=true");
    expect(url).toContain("force=true");
  });

  it("throws a descriptive error on HTTP 403 (provider disabled)", async () => {
    vi.stubGlobal("fetch", mockFetchHttpError(403, "Provider not ready"));

    await expect(classifyBackfill()).rejects.toThrow("403");
  });
});

// ── resetRssData ──────────────────────────────────────────────────────────────

describe("resetRssData", () => {
  it("calls POST /api/dev/reset-rss-data", async () => {
    const payload = { status: "ok", deleted_articles: 30, deleted_ingestion_runs: 5 };
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await resetRssData();

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/dev/reset-rss-data");
    expect(options.method).toBe("POST");
    expect(result).toEqual(payload);
  });

  it("throws a descriptive error on 403 (ALLOW_DEV_RESET not set)", async () => {
    vi.stubGlobal("fetch", mockFetchHttpError(403, "Dev reset is disabled. Set ALLOW_DEV_RESET=true"));

    await expect(resetRssData()).rejects.toThrow("403");
    await expect(resetRssData()).rejects.toThrow("ALLOW_DEV_RESET");
  });

  it("throws a descriptive error on network failure", async () => {
    vi.stubGlobal("fetch", mockFetchNetworkError("Connection refused"));

    await expect(resetRssData()).rejects.toThrow("Cannot reach backend");
  });
});

// ── PR 13: scheduler + source-health client functions ─────────────────────────

import { getSchedulerStatus, runSchedulerNow, getSourceHealth, isIngestionBusyError } from "./client";

describe("getSchedulerStatus", () => {
  it("calls GET /api/ingest/scheduler/status", async () => {
    const payload = { enabled: false, running: false, interval_minutes: 15 };
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await getSchedulerStatus();

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/ingest/scheduler/status");
    expect(options?.method).toBeUndefined(); // GET
    expect(result).toEqual(payload);
  });
});

describe("runSchedulerNow", () => {
  it("calls POST /api/ingest/scheduler/run-now", async () => {
    const payload = { trigger: "run_now", status: "ok", sources: [] };
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await runSchedulerNow();

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/ingest/scheduler/run-now");
    expect(options.method).toBe("POST");
    expect(result).toEqual(payload);
  });

  it("surfaces 409 conflict in the thrown error", async () => {
    vi.stubGlobal("fetch", mockFetchHttpError(409, {
      error: "ingestion_already_running",
      message: "ייבוא פעיל כרגע",
    }));

    await expect(runSchedulerNow()).rejects.toThrow("409");
  });
});

describe("getSourceHealth", () => {
  it("calls GET /api/ingest/source-health", async () => {
    const payload = [{ source_id: "walla_sport", freshness: "healthy" }];
    const mockFetch = mockFetchSuccess(payload);
    vi.stubGlobal("fetch", mockFetch);

    const result = await getSourceHealth();

    expect(mockFetch.mock.calls[0][0]).toContain("/api/ingest/source-health");
    expect(result).toEqual(payload);
  });
});

describe("isIngestionBusyError", () => {
  it("detects 409 status in error message", () => {
    expect(isIngestionBusyError(new Error("API POST /api/ingest/run failed (409): busy"))).toBe(true);
  });

  it("detects ingestion_already_running in error message", () => {
    expect(isIngestionBusyError(new Error('{"error":"ingestion_already_running"}'))).toBe(true);
  });

  it("returns false for other errors", () => {
    expect(isIngestionBusyError(new Error("API GET /api/feed failed (500): oops"))).toBe(false);
    expect(isIngestionBusyError(null)).toBe(false);
    expect(isIngestionBusyError(undefined)).toBe(false);
  });
});
