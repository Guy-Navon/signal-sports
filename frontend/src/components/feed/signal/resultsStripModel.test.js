import { describe, expect, it } from "vitest";
import { normalizeResultFromApi, statusLabel } from "@/components/results/resultsModel";
import { latestFinals, resultStripLabels, resultWinner, RESULTS_STRIP_LIMIT } from "./resultsStripModel";

const NOW = Date.parse("2026-11-14T12:00:00Z");
const game = (id, over = {}) => ({
  id,
  status: "final",
  startTime: "2026-11-14T10:00:00Z",
  competitionHe: "יורוליג",
  home: { name: "מכבי תל אביב", score: 89 },
  away: { name: "ריאל מדריד", score: 85 },
  winner: "home",
  ...over,
});

describe("latestFinals", () => {
  it("selects only completed games with both finite scores, including zero", () => {
    const final = game("final");
    const draw = game("draw", { home: { name: "בית", score: 0 }, away: { name: "חוץ", score: 0 }, winner: "draw" });
    const others = ["live", "scheduled", "postponed", "cancelled", "unknown"].map((status) => game(status, { status }));
    expect(latestFinals([
      ...others, final, draw,
      game("missing", { home: { score: null } }),
      game("nan", { away: { score: NaN } }),
      game("infinite", { away: { score: Infinity } }),
    ], NOW)).toEqual([final, draw]);
  });

  it("takes the ten most recent finals, without mutating or cloning the supplied games", () => {
    const games = Object.freeze(Array.from({ length: 14 }, (_, index) => Object.freeze(game(String(index), {
      startTime: new Date(NOW - (index + 1) * 3_600_000).toISOString(),
    }))).reverse());
    const selected = latestFinals(games, NOW);
    expect(RESULTS_STRIP_LIMIT).toBe(10);
    expect(selected.map(({ id }) => id)).toEqual(Array.from({ length: 10 }, (_, i) => String(i)));
    expect(selected[0]).toBe(games[13]);
    expect(games[0].id).toBe("13");
  });

  it("keeps input order for tied times and excludes unknown or future times", () => {
    expect(latestFinals([
      game("first"), game("second"),
      game("missing", { startTime: null }),
      game("invalid", { startTime: "not a date" }),
      game("future", { startTime: "2026-11-15T12:00:00Z" }),
    ], NOW).map(({ id }) => id)).toEqual(["first", "second"]);
  });

  it("is empty for an omitted, empty or non-final results set", () => {
    expect(latestFinals(undefined, NOW)).toEqual([]);
    expect(latestFinals([], NOW)).toEqual([]);
    expect(latestFinals([game("live", { status: "live" })], NOW)).toEqual([]);
  });
});

describe("resultWinner", () => {
  it("uses the same declared winner as the results page, rather than deriving another decision", () => {
    expect(resultWinner(game("home"))).toBe("home");
    expect(resultWinner(game("away", { winner: "away" }))).toBe("away");
  });

  it("has no winner for a draw, an unknown winner or an unfinished game", () => {
    for (const winner of ["draw", null, undefined]) {
      expect(resultWinner(game("none", { winner }))).toBeNull();
    }
    expect(resultWinner(game("live", { status: "live" }))).toBeNull();
    expect(resultWinner(game("missing", { away: { score: null } }))).toBeNull();
  });
});

describe("resultStripLabels", () => {
  it("reuses normalized Hebrew names and competition labels and describes the completed score", () => {
    const normalized = normalizeResultFromApi({
      id: "api", competition_id: "comp:euroleague", competition_he: "יורוליג",
      start_time: "2026-11-14T10:00:00Z", status: "final", winner: "home",
      home: { name: "מכבי תל אביב", name_provider: "Maccabi Tel Aviv", score: 89 },
      away: { name: "ריאל מדריד", name_provider: "Real Madrid", score: 85 },
    });
    expect(resultStripLabels(normalized, NOW)).toEqual({
      competition: "יורוליג",
      relativeTime: "לפני שעתיים",
      description: `מכבי תל אביב 89, ריאל מדריד 85, ${statusLabel("final")}`,
    });
  });

  it("preserves provider English names when the results page has no Hebrew name", () => {
    const normalized = normalizeResultFromApi({
      id: "english", competition_id: "comp:eurocup", competition_he: "יורוקאפ",
      start_time: "2026-11-13T12:00:00Z", status: "final",
      home: { name_provider: "London Lions", score: 0 },
      away: { name: "הפועל ירושלים", score: 1 },
    });
    expect(resultStripLabels(normalized, NOW)).toEqual({
      competition: "יורוקאפ", relativeTime: "אתמול",
      description: `London Lions 0, הפועל ירושלים 1, ${statusLabel("final")}`,
    });
  });
});
