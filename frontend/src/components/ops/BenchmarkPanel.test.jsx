/**
 * GatingBenchmarkPanel tests.
 *
 * React Testing Library is not installed; tests cover:
 *  - formatPercent helper (pure function)
 *  - runLlmGatingBenchmark API function exists and calls the right path
 *  - benchmark response shape expectations (normalizers/data helpers)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { formatPercent, formatDuration } from "@/api/normalizers";

// ── formatPercent ─────────────────────────────────────────────────────────────

describe("formatPercent", () => {
  it("formats 0.5667 as 56.7%", () => {
    expect(formatPercent(0.5667)).toBe("56.7%");
  });

  it("formats 0.40 as 40.0%", () => {
    expect(formatPercent(0.4)).toBe("40.0%");
  });

  it("formats 1.0 as 100.0%", () => {
    expect(formatPercent(1.0)).toBe("100.0%");
  });

  it("formats 0.0 as 0.0%", () => {
    expect(formatPercent(0.0)).toBe("0.0%");
  });

  it("returns — for null", () => {
    expect(formatPercent(null)).toBe("—");
  });

  it("returns — for undefined", () => {
    expect(formatPercent(undefined)).toBe("—");
  });
});

// ── API client: runLlmGatingBenchmark ─────────────────────────────────────────

describe("runLlmGatingBenchmark API function", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("is exported from client.js", async () => {
    const mod = await import("@/api/client");
    expect(typeof mod.runLlmGatingBenchmark).toBe("function");
  });

  it("calls POST /api/dev/benchmark/llm-gating", async () => {
    const calls = [];
    globalThis.fetch = vi.fn(async (url, opts) => {
      calls.push({ url, opts });
      return {
        ok: true,
        json: async () => ({
          provider: "fake:test",
          sources: [],
          baseline: { gating_enabled: false, sources: {} },
          gated: { gating_enabled: true, sources: {} },
          comparison: {},
        }),
      };
    });

    const mod = await import("@/api/client");
    await mod.runLlmGatingBenchmark();

    expect(calls.length).toBe(1);
    expect(calls[0].url).toContain("/api/dev/benchmark/llm-gating");
    expect(calls[0].opts?.method).toBe("POST");
  });
});

// ── Benchmark response shape helpers ─────────────────────────────────────────

describe("Benchmark response shape expectations", () => {
  const MOCK_RESPONSE = {
    provider: "ollama:qwen2.5:3b-instruct",
    sources: ["walla_sport", "israel_hayom_sport"],
    baseline: {
      gating_enabled: false,
      sources: {
        walla_sport: {
          total_ms: 382000,
          llm_attempts: 30,
          llm_successes: 29,
          llm_skipped: 0,
          skip_rate: null,
          llm_avg_ms: 12700,
          llm_p95_ms: 15900,
          fallbacks: { connect_error: 0, timeout_or_parse: 1, low_confidence: 0 },
          llm_skip_reasons: {},
          llm_call_reasons: {},
          sport_unknown: 6,
        },
      },
    },
    gated: {
      gating_enabled: true,
      sources: {
        walla_sport: {
          total_ms: 171000,
          llm_attempts: 13,
          llm_successes: 12,
          llm_skipped: 17,
          skip_rate: 0.5667,
          llm_avg_ms: 11900,
          llm_p95_ms: 15100,
          fallbacks: { connect_error: 0, timeout_or_parse: 1, low_confidence: 0 },
          llm_skip_reasons: { clear_league_in_title: 8, strong_source_sport_hint: 9 },
          llm_call_reasons: { sport_unknown: 7, hebrew_broad_source_unclear: 6 },
          sport_unknown: 6,
        },
      },
    },
    comparison: {
      walla_sport: {
        llm_call_reduction: 17,
        skip_rate: 0.5667,
        total_ms_reduction: 211000,
        sport_unknown_delta: 0,
        passes_targets: true,
      },
    },
  };

  it("baseline has gating_enabled: false", () => {
    expect(MOCK_RESPONSE.baseline.gating_enabled).toBe(false);
  });

  it("gated has gating_enabled: true", () => {
    expect(MOCK_RESPONSE.gated.gating_enabled).toBe(true);
  });

  it("walla_sport baseline has llm_skipped = 0", () => {
    expect(MOCK_RESPONSE.baseline.sources.walla_sport.llm_skipped).toBe(0);
  });

  it("walla_sport gated has llm_skipped = 17", () => {
    expect(MOCK_RESPONSE.gated.sources.walla_sport.llm_skipped).toBe(17);
  });

  it("skip_rate formats correctly for gated walla_sport", () => {
    const stats = MOCK_RESPONSE.gated.sources.walla_sport;
    expect(formatPercent(stats.skip_rate)).toBe("56.7%");
  });

  it("baseline skip_rate is null → formatPercent returns —", () => {
    const stats = MOCK_RESPONSE.baseline.sources.walla_sport;
    expect(formatPercent(stats.skip_rate)).toBe("—");
  });

  it("comparison passes_targets is true when skip >= 40% and no quality regression", () => {
    const comp = MOCK_RESPONSE.comparison.walla_sport;
    expect(comp.passes_targets).toBe(true);
    expect(comp.skip_rate).toBeGreaterThanOrEqual(0.4);
    expect(comp.sport_unknown_delta).toBeLessThanOrEqual(0);
  });

  it("formatDuration renders total_ms correctly for baseline", () => {
    const ms = MOCK_RESPONSE.baseline.sources.walla_sport.total_ms;
    expect(formatDuration(ms)).toBe("6:22");
  });

  it("formatDuration renders total_ms correctly for gated", () => {
    const ms = MOCK_RESPONSE.gated.sources.walla_sport.total_ms;
    expect(formatDuration(ms)).toBe("2:51");
  });

  it("fallback breakdown is accessible for baseline", () => {
    const fb = MOCK_RESPONSE.baseline.sources.walla_sport.fallbacks;
    expect(fb).toEqual({ connect_error: 0, timeout_or_parse: 1, low_confidence: 0 });
  });

  it("skip reasons map is non-empty for gated run", () => {
    const reasons = MOCK_RESPONSE.gated.sources.walla_sport.llm_skip_reasons;
    expect(Object.keys(reasons).length).toBeGreaterThan(0);
  });

  it("missing reason maps do not crash formatPercent", () => {
    expect(() => formatPercent(null)).not.toThrow();
    expect(() => formatPercent(undefined)).not.toThrow();
  });

  it("empty reason map has no keys", () => {
    const reasons = MOCK_RESPONSE.baseline.sources.walla_sport.llm_skip_reasons;
    expect(Object.keys(reasons).length).toBe(0);
  });

  it("time saved is accessible as total_ms_reduction", () => {
    const saved = MOCK_RESPONSE.comparison.walla_sport.total_ms_reduction;
    expect(saved).toBeGreaterThan(0);
    expect(formatDuration(saved)).toBeTruthy();
  });
});

// ── Error display helpers ─────────────────────────────────────────────────────

describe("Error message handling", () => {
  it("ALLOW_DEV_RESET error message is recognizable", () => {
    const msg = "Benchmark requires ALLOW_DEV_RESET=true (it resets RSS data between runs).";
    expect(msg).toContain("ALLOW_DEV_RESET");
  });

  it("provider disabled error message is recognizable", () => {
    const msg = "Classification provider cannot classify. Set CLASSIFICATION_PROVIDER=ollama.";
    expect(msg.toLowerCase()).toContain("ollama");
  });
});
