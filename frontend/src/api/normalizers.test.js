import { describe, it, expect } from "vitest";
import {
  normalizeArticleFromApi,
  normalizeProfileFromApi,
  normalizeScoredArticleFromApi,
  normalizeCalibrationHeadlineFromApi,
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
