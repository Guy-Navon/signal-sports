import { expect, it } from "vitest";
import { groupResults, chosenLineText, pageState } from "./resultsPageModel";
import { normalizeResultFromApi } from "./resultsModel";
const now = new Date("2026-11-15T12:00:00Z");
const game = (id, date, more = {}) => ({ id, localDate: date, startTime: date ? `${date}T10:00:00Z` : null,
  status: "final", sport: "basketball", competitionId: "comp:nba", competitionHe: "NBA", ...more });
it("orders today, ascending upcoming days, descending past days and undated last", () => {
  const groups = groupResults([game("old", "2026-11-13"), game("tomorrow", "2026-11-16", { status: "scheduled" }),
    game("today", "2026-11-15"), game("later", "2026-11-17", { status: "scheduled" }),
    game("yesterday", "2026-11-14"), game("undated", null), game("live", "2026-11-15", { status: "live" })], now);
  expect(groups.map(g => g.dayKey)).toEqual(["2026-11-15", "2026-11-16", "2026-11-17", "2026-11-14", "2026-11-13", null]);
  expect(JSON.stringify(groups)).not.toContain('"live"');
});
it("groups date then sport then competition, trusts the API local date and sorts kickoff times", () => {
  const groups = groupResults([game("late", "2026-11-15", { startTime: "2026-11-15T18:00:00Z", status: "scheduled" }),
    game("early", "2026-11-15", { startTime: "2026-11-15T16:00:00Z", status: "scheduled" }),
    game("football", "2026-11-15", { sport: "football", competitionId: "comp:ligat_haal" }),
    game("el", "2026-11-15", { competitionId: "comp:euroleague" })], now);
  expect(groups).toHaveLength(1);
  expect(groups[0].sports.map(s => s.sport)).toEqual(["basketball", "football"]);
  expect(groups[0].sports[0].leagues.find(l => l.competitionId === "comp:nba").games.map(g => g.id)).toEqual(["early", "late"]);
});
it("preserves authoritative enrichment and handles missing detail without deriving a player's line", () => {
  const leaders = [{ side: "home", name: "דני אבדיה", stat: "points", value: 34 }];
  const row = normalizeResultFromApi({ id: "a", home: { rank: 5 }, leaders, chosen_player_lines: [], local_date: "2026-11-15", detail_available: true });
  expect(row.home.rank).toBe(5); expect(row.leaders).toBe(leaders); expect(row.chosenPlayerLines).toEqual([]);
  expect(row.localDate).toBe("2026-11-15"); expect(row.detailAvailable).toBe(true);
  expect(normalizeResultFromApi({ id: "b" }).detailAvailable).toBe(false);
});
it("formats only available chosen stats, including zeroes, with no invented values", () => {
  expect(chosenLineText({ stats: { points: 34, rebounds: 6, assists: 0 }, minutes: 35.5 }, "basketball")).toContain("34");
  expect(chosenLineText({ stats: {}, minutes: null }, "football")).toBe("");
});
it("distinguishes loading, retryable error, no preferences, empty and ready", () => {
  expect(pageState({ loading: true, games: [] })).toBe("loading");
  expect(pageState({ error: "down", games: [] })).toBe("error");
  expect(pageState({ hasPreferences: false, games: [] })).toBe("preferences");
  expect(pageState({ hasPreferences: true, games: [] })).toBe("empty");
  expect(pageState({ hasPreferences: true, games: [game("a", "2026-11-15")] })).toBe("ready");
});
