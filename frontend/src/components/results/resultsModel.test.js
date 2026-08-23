import { describe, it, expect } from "vitest";
import {
  normalizeResultFromApi,
  normalizeResultsResponse,
  statusLabel,
  isCompleted,
  hasScore,
  RESULT_STATUS,
} from "./resultsModel";

const RAW = {
  id: "game_1",
  competition_id: "comp:nba",
  competition_he: "NBA",
  competition_en: "NBA",
  sport: "basketball",
  season: "2025-2026",
  stage: "עונה סדירה",
  status: "final",
  start_time: "2026-04-10T02:00:00+00:00",
  home: { id: "team:portland_blazers", name: "פורטלנד", name_provider: "Portland", score: 110, is_winner: true },
  away: { id: "team:washington_wizards", name: "וושינגטון", name_provider: "Washington", score: 98, is_winner: false },
  winner: "home",
  relevance_reason: "followed_competition:comp:nba",
};

describe("normalizeResultFromApi", () => {
  it("maps snake_case API fields to camelCase", () => {
    const g = normalizeResultFromApi(RAW);
    expect(g.competitionId).toBe("comp:nba");
    expect(g.competitionHe).toBe("NBA");
    expect(g.startTime).toBe("2026-04-10T02:00:00+00:00");
    expect(g.home).toEqual({
      id: "team:portland_blazers", name: "פורטלנד",
      nameProvider: "Portland", score: 110, isWinner: true,
    });
    expect(g.away.isWinner).toBe(false);
    expect(g.winner).toBe("home");
    expect(g.relevanceReason).toBe("followed_competition:comp:nba");
  });

  it("falls back to name_provider when a display name is missing", () => {
    const g = normalizeResultFromApi({ ...RAW, home: { name_provider: "Only Provider" } });
    expect(g.home.name).toBe("Only Provider");
    expect(g.home.score).toBeNull();
    expect(g.home.isWinner).toBe(false);
  });
});

describe("normalizeResultsResponse", () => {
  it("normalizes has_preferences and games", () => {
    const r = normalizeResultsResponse({ has_preferences: true, games: [RAW] });
    expect(r.hasPreferences).toBe(true);
    expect(r.games).toHaveLength(1);
    expect(r.games[0].id).toBe("game_1");
  });

  it("is defensive against missing fields", () => {
    expect(normalizeResultsResponse(undefined)).toEqual({ hasPreferences: false, games: [] });
    expect(normalizeResultsResponse({}).games).toEqual([]);
  });
});

describe("status helpers", () => {
  it("labels statuses in Hebrew", () => {
    expect(statusLabel(RESULT_STATUS.FINAL)).toBe("תוצאה סופית");
    expect(statusLabel(RESULT_STATUS.POSTPONED)).toBe("נדחה");
    expect(statusLabel("nonsense")).toBe("");
  });

  it("isCompleted only for final", () => {
    expect(isCompleted(RESULT_STATUS.FINAL)).toBe(true);
    expect(isCompleted(RESULT_STATUS.SCHEDULED)).toBe(false);
  });

  it("hasScore detects both scores present", () => {
    expect(hasScore(normalizeResultFromApi(RAW))).toBe(true);
    const sched = normalizeResultFromApi({ ...RAW, home: { score: null }, away: { score: null } });
    expect(hasScore(sched)).toBe(false);
  });
});
