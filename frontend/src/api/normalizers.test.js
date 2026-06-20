import { describe, it, expect } from "vitest";
import {
  normalizeArticleFromApi,
  normalizeProfileFromApi,
  normalizeScoredArticleFromApi,
  normalizeCalibrationHeadlineFromApi,
  normalizeIngestResultFromApi,
  formatMs,
  formatDuration,
} from "./normalizers";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const RAW_ARTICLE = {
  id: "article_001",
  source: "sport5",
  source_display_name: "ספורט 5",
  url: "https://sport5.co.il/1",
  title: "דיווח: מכבי ת״א במו״מ",
  original_title: null,
  translated_title: null,
  language: "he",
  published_at: "2026-06-11T08:00:00Z",
  sport: "basketball",
  league: "EuroLeague",
  entities: ["Maccabi Tel Aviv Basketball"],
  event_type: "negotiation",
  importance: "high",
  confidence: 0.92,
  tags: ["מכבי ת״א", "יורוליג"],
  cluster_id: "cluster_001",
};

const RAW_SCORED_ARTICLE = {
  article: RAW_ARTICLE,
  decision: "push",
  matched_topic: "maccabi_tel_aviv_basketball",
  matched_event_rule: "negotiation",
  reasoning: ["פרופיל: Guy", "נושא: מכבי ת״א כדורסל", "החלטה סופית: דורש תשומת לב"],
};

const RAW_PROFILE = {
  user_id: "guy",
  display_name: "Guy",
  language: "he",
  profile_type: "basketball_power_user",
  muted_topics: ["football"],
  muted_sources: [],
  followed_entities: ["Maccabi Tel Aviv Basketball"],
  topics: [
    {
      topic_id: "maccabi_tel_aviv_basketball",
      label: "מכבי ת״א כדורסל",
      sport: "basketball",
      priority: 100,
      mode: "all",
      scope: "entity",
      leagues: ["EuroLeague", "Israeli Basketball League"],
      entities: ["Maccabi Tel Aviv Basketball"],
      event_rules: { negotiation: "push", signing: "push" },
      entity_event_rules: null,
      muted_subtopics: [],
    },
  ],
};

const RAW_CALIBRATION_HEADLINE = {
  id: "calibration_001",
  title: "מכבי ת״א במו״מ עם גארד מיורוליג",
  sport: "basketball",
  league: "EuroLeague",
  entities: ["Maccabi Tel Aviv Basketball"],
  event_type: "negotiation",
  importance: "high",
  tags: ["מכבי", "יורוליג", "מו״מ"],
};

// ── Article normalizer ────────────────────────────────────────────────────────

describe("normalizeArticleFromApi", () => {
  it("converts snake_case fields to camelCase", () => {
    const result = normalizeArticleFromApi(RAW_ARTICLE);
    expect(result.sourceDisplayName).toBe("ספורט 5");
    expect(result.originalTitle).toBeNull();
    expect(result.translatedTitle).toBeNull();
    expect(result.publishedAt).toBe("2026-06-11T08:00:00Z");
    expect(result.eventType).toBe("negotiation");
    expect(result.clusterId).toBe("cluster_001");
  });

  it("preserves unchanged scalar fields", () => {
    const result = normalizeArticleFromApi(RAW_ARTICLE);
    expect(result.id).toBe("article_001");
    expect(result.source).toBe("sport5");
    expect(result.url).toBe("https://sport5.co.il/1");
    expect(result.title).toBe("דיווח: מכבי ת״א במו״מ");
    expect(result.language).toBe("he");
    expect(result.sport).toBe("basketball");
    expect(result.league).toBe("EuroLeague");
    expect(result.importance).toBe("high");
    expect(result.confidence).toBe(0.92);
  });

  it("preserves array fields", () => {
    const result = normalizeArticleFromApi(RAW_ARTICLE);
    expect(result.entities).toEqual(["Maccabi Tel Aviv Basketball"]);
    expect(result.tags).toEqual(["מכבי ת״א", "יורוליג"]);
  });

  it("defaults missing optional fields", () => {
    const minimal = {
      id: "x", source: "s", source_display_name: "S", url: "http://s",
      title: "T", language: "he", published_at: "2026-01-01T00:00:00Z",
      sport: "basketball", event_type: "signing", importance: "medium",
    };
    const result = normalizeArticleFromApi(minimal);
    expect(result.originalTitle).toBeNull();
    expect(result.translatedTitle).toBeNull();
    expect(result.league).toBeNull();
    expect(result.entities).toEqual([]);
    expect(result.tags).toEqual([]);
    expect(result.clusterId).toBeNull();
    expect(result.confidence).toBe(0.85);
  });

  it("preserves subtitle when present", () => {
    const withSubtitle = {
      ...RAW_ARTICLE,
      subtitle: "The club closed a deal with a EuroLeague guard.",
    };
    const result = normalizeArticleFromApi(withSubtitle);
    expect(result.subtitle).toBe("The club closed a deal with a EuroLeague guard.");
  });

  it("returns null subtitle when API returns null", () => {
    const withNull = { ...RAW_ARTICLE, subtitle: null };
    const result = normalizeArticleFromApi(withNull);
    expect(result.subtitle).toBeNull();
  });

  it("returns null subtitle when subtitle field is absent", () => {
    const result = normalizeArticleFromApi(RAW_ARTICLE);
    expect(result.subtitle).toBeNull();
  });
});

// ── Scored article normalizer ─────────────────────────────────────────────────

describe("normalizeScoredArticleFromApi", () => {
  it("flattens article fields to the top level", () => {
    const result = normalizeScoredArticleFromApi(RAW_SCORED_ARTICLE);
    expect(result.id).toBe("article_001");
    expect(result.sourceDisplayName).toBe("ספורט 5");
    expect(result.eventType).toBe("negotiation");
    expect(result.publishedAt).toBe("2026-06-11T08:00:00Z");
  });

  it("creates a score sub-object with camelCase fields", () => {
    const result = normalizeScoredArticleFromApi(RAW_SCORED_ARTICLE);
    expect(result.score).toBeDefined();
    expect(result.score.decision).toBe("push");
    expect(result.score.matchedTopic).toBe("maccabi_tel_aviv_basketball");
    expect(result.score.matchedRule).toBe("negotiation");
    expect(result.score.reasoning).toHaveLength(3);
  });

  it("maps matched_event_rule to matchedRule (not matchedEventRule)", () => {
    const result = normalizeScoredArticleFromApi(RAW_SCORED_ARTICLE);
    expect(result.score.matchedRule).toBe("negotiation");
    expect(result.score.matchedEventRule).toBeUndefined();
  });

  it("adds type: article", () => {
    const result = normalizeScoredArticleFromApi(RAW_SCORED_ARTICLE);
    expect(result.type).toBe("article");
  });

  it("includes Hebrew label from decision", () => {
    const result = normalizeScoredArticleFromApi(RAW_SCORED_ARTICLE);
    expect(result.score.label).toBe("דורש תשומת לב");
  });

  it("handles null matched_topic and matched_event_rule", () => {
    const noMatch = { ...RAW_SCORED_ARTICLE, decision: "hidden", matched_topic: null, matched_event_rule: null };
    const result = normalizeScoredArticleFromApi(noMatch);
    expect(result.score.matchedTopic).toBeNull();
    expect(result.score.matchedRule).toBeNull();
    expect(result.score.decision).toBe("hidden");
  });
});

// ── Profile normalizer ────────────────────────────────────────────────────────

describe("normalizeProfileFromApi", () => {
  it("converts snake_case profile fields to camelCase", () => {
    const result = normalizeProfileFromApi(RAW_PROFILE);
    expect(result.userId).toBe("guy");
    expect(result.displayName).toBe("Guy");
    expect(result.profileType).toBe("basketball_power_user");
    expect(result.mutedTopics).toEqual(["football"]);
    expect(result.mutedSources).toEqual([]);
    expect(result.followedEntities).toEqual(["Maccabi Tel Aviv Basketball"]);
  });

  it("normalizes nested topic preferences", () => {
    const result = normalizeProfileFromApi(RAW_PROFILE);
    expect(result.topics).toHaveLength(1);
    const topic = result.topics[0];
    expect(topic.topicId).toBe("maccabi_tel_aviv_basketball");
    expect(topic.eventRules).toEqual({ negotiation: "push", signing: "push" });
    expect(topic.entityEventRules).toBeNull();
    expect(topic.mutedSubtopics).toEqual([]);
    expect(topic.scope).toBe("entity");
    expect(topic.leagues).toEqual(["EuroLeague", "Israeli Basketball League"]);
  });

  it("defaults missing optional profile fields", () => {
    const minimal = {
      user_id: "test", display_name: "Test", profile_type: "basic",
    };
    const result = normalizeProfileFromApi(minimal);
    expect(result.mutedTopics).toEqual([]);
    expect(result.mutedSources).toEqual([]);
    expect(result.followedEntities).toEqual([]);
    expect(result.topics).toEqual([]);
    expect(result.language).toBe("he");
  });
});

// ── Ingest result normalizer ──────────────────────────────────────────────────

const RAW_INGEST_RESULT_LLM_ACTIVE = {
  source_id: "walla_sport",
  fetched: 30,
  inserted: 10,
  skipped_duplicate: 5,
  skipped_filtered: 15,
  failed: 0,
  errors: [],
  fetch_ms: 420.5,
  total_ms: 104300.0,
  llm_attempts: 10,
  llm_successes: 9,
  llm_fallback_connect_error: 0,
  llm_fallback_timeout_or_parse: 1,
  llm_fallback_low_confidence: 0,
  llm_avg_ms: 2900.0,
  llm_p95_ms: 5800.0,
};

const RAW_INGEST_RESULT_LLM_DISABLED = {
  source_id: "israel_hayom_sport",
  fetched: 100,
  inserted: 21,
  skipped_duplicate: 0,
  skipped_filtered: 79,
  failed: 0,
  errors: [],
  fetch_ms: 310.0,
  total_ms: 1440.0,
  llm_attempts: 0,
  llm_successes: 0,
  llm_fallback_connect_error: 0,
  llm_fallback_timeout_or_parse: 0,
  llm_fallback_low_confidence: 0,
  llm_avg_ms: null,
  llm_p95_ms: null,
};

describe("normalizeIngestResultFromApi", () => {
  it("maps snake_case fields to camelCase", () => {
    const r = normalizeIngestResultFromApi(RAW_INGEST_RESULT_LLM_ACTIVE);
    expect(r.sourceId).toBe("walla_sport");
    expect(r.skippedDuplicate).toBe(5);
    expect(r.skippedFiltered).toBe(15);
    expect(r.fetchMs).toBe(420.5);
    expect(r.totalMs).toBe(104300.0);
    expect(r.llmAttempts).toBe(10);
    expect(r.llmSuccesses).toBe(9);
    expect(r.llmFallbackConnectError).toBe(0);
    expect(r.llmFallbackTimeoutOrParse).toBe(1);
    expect(r.llmFallbackLowConfidence).toBe(0);
    expect(r.llmAvgMs).toBe(2900.0);
    expect(r.llmP95Ms).toBe(5800.0);
  });

  it("preserves direct-mapped fields", () => {
    const r = normalizeIngestResultFromApi(RAW_INGEST_RESULT_LLM_ACTIVE);
    expect(r.fetched).toBe(30);
    expect(r.inserted).toBe(10);
    expect(r.failed).toBe(0);
    expect(r.errors).toEqual([]);
  });

  it("sets llmAttempts=0 when LLM is disabled — used by UI to show 'LLM לא הופעל'", () => {
    const r = normalizeIngestResultFromApi(RAW_INGEST_RESULT_LLM_DISABLED);
    expect(r.llmAttempts).toBe(0);
    expect(r.llmAvgMs).toBeNull();
    expect(r.llmP95Ms).toBeNull();
  });

  it("defaults all missing timing fields to 0 or null", () => {
    const r = normalizeIngestResultFromApi({
      source_id: "x", fetched: 0, inserted: 0,
    });
    expect(r.fetchMs).toBeNull();
    expect(r.totalMs).toBeNull();
    expect(r.llmAttempts).toBe(0);
    expect(r.llmSuccesses).toBe(0);
    expect(r.llmFallbackConnectError).toBe(0);
    expect(r.llmFallbackTimeoutOrParse).toBe(0);
    expect(r.llmFallbackLowConfidence).toBe(0);
    expect(r.llmAvgMs).toBeNull();
    expect(r.llmP95Ms).toBeNull();
    expect(r.errors).toEqual([]);
  });

  it("sets llmFallbackConnectError from raw field when non-zero", () => {
    const r = normalizeIngestResultFromApi({
      ...RAW_INGEST_RESULT_LLM_ACTIVE,
      llm_fallback_connect_error: 3,
    });
    expect(r.llmFallbackConnectError).toBe(3);
  });

  it("maps llm_skipped and reason dicts from API response", () => {
    const r = normalizeIngestResultFromApi({
      ...RAW_INGEST_RESULT_LLM_ACTIVE,
      llm_skipped: 12,
      llm_skip_reasons: { clear_league_in_title: 8, strong_source_sport_hint: 4 },
      llm_call_reasons: { sport_unknown: 5, ambiguous_club: 3 },
    });
    expect(r.llmSkipped).toBe(12);
    expect(r.llmSkipReasons).toEqual({ clear_league_in_title: 8, strong_source_sport_hint: 4 });
    expect(r.llmCallReasons).toEqual({ sport_unknown: 5, ambiguous_club: 3 });
  });

  it("defaults llmSkipped to 0 when absent — old API responses remain backward-compatible", () => {
    const r = normalizeIngestResultFromApi({ source_id: "x", fetched: 0, inserted: 0 });
    expect(r.llmSkipped).toBe(0);
    expect(r.llmSkipReasons).toEqual({});
    expect(r.llmCallReasons).toEqual({});
  });
});

// ── formatMs ──────────────────────────────────────────────────────────────────

describe("formatMs", () => {
  it("returns '—' for null", () => {
    expect(formatMs(null)).toBe("—");
  });

  it("returns '—' for undefined", () => {
    expect(formatMs(undefined)).toBe("—");
  });

  it("formats values under 1000ms as integers with 'ms' suffix", () => {
    expect(formatMs(0)).toBe("0ms");
    expect(formatMs(420)).toBe("420ms");
    expect(formatMs(999)).toBe("999ms");
  });

  it("rounds sub-ms values to integers", () => {
    expect(formatMs(420.7)).toBe("421ms");
    expect(formatMs(420.3)).toBe("420ms");
  });

  it("formats values >= 1000ms as decimal seconds", () => {
    expect(formatMs(1000)).toBe("1.0s");
    expect(formatMs(2900)).toBe("2.9s");
    expect(formatMs(5800)).toBe("5.8s");
    expect(formatMs(10000)).toBe("10.0s");
  });

  it("formats exactly 1000ms as '1.0s'", () => {
    expect(formatMs(1000)).toBe("1.0s");
  });
});

// ── formatDuration ────────────────────────────────────────────────────────────

describe("formatDuration", () => {
  it("returns '—' for null", () => {
    expect(formatDuration(null)).toBe("—");
  });

  it("returns '—' for undefined", () => {
    expect(formatDuration(undefined)).toBe("—");
  });

  it("formats values < 60 000ms as decimal seconds", () => {
    expect(formatDuration(1440)).toBe("1.4s");
    expect(formatDuration(12300)).toBe("12.3s");
    expect(formatDuration(59999)).toBe("60.0s");
  });

  it("formats values >= 60 000ms as minutes:seconds", () => {
    expect(formatDuration(60000)).toBe("1:00");
    expect(formatDuration(104300)).toBe("1:44");
    expect(formatDuration(125000)).toBe("2:05");
    expect(formatDuration(3600000)).toBe("60:00");
  });

  it("zero-pads seconds below 10", () => {
    expect(formatDuration(60000 + 5000)).toBe("1:05");
    expect(formatDuration(60000 + 9000)).toBe("1:09");
    expect(formatDuration(60000 + 10000)).toBe("1:10");
  });
});

// ── Calibration headline normalizer ──────────────────────────────────────────

describe("normalizeCalibrationHeadlineFromApi", () => {
  it("converts event_type to eventType", () => {
    const result = normalizeCalibrationHeadlineFromApi(RAW_CALIBRATION_HEADLINE);
    expect(result.eventType).toBe("negotiation");
    expect(result.event_type).toBeUndefined();
  });

  it("preserves other fields", () => {
    const result = normalizeCalibrationHeadlineFromApi(RAW_CALIBRATION_HEADLINE);
    expect(result.id).toBe("calibration_001");
    expect(result.title).toBe("מכבי ת״א במו״מ עם גארד מיורוליג");
    expect(result.sport).toBe("basketball");
    expect(result.league).toBe("EuroLeague");
    expect(result.entities).toEqual(["Maccabi Tel Aviv Basketball"]);
    expect(result.importance).toBe("high");
    expect(result.tags).toEqual(["מכבי", "יורוליג", "מו״מ"]);
  });

  it("defaults missing optional fields", () => {
    const minimal = {
      id: "h1", title: "Test", sport: "basketball",
      event_type: "signing", importance: "medium",
    };
    const result = normalizeCalibrationHeadlineFromApi(minimal);
    expect(result.league).toBeNull();
    expect(result.entities).toEqual([]);
    expect(result.tags).toEqual([]);
  });
});
