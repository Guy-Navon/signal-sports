import { describe, expect, it } from "vitest";
import { collapseLeague, dateChips, followedTeamIds, leadersText, playerLines, sideBoxes, streamDays,
  summaryParts, tileEntries, tileVerdict } from "./resultsLayoutModel";

const now = new Date("2026-11-15T12:00:00Z");
const team = (id, score, rank = null) => ({ id, name: id, score, rank, isWinner: false });
const game = (id, date, more = {}) => ({ id, localDate: date, startTime: date ? `${date}T${more.time || "18:00:00"}Z` : null, status: "final",
  sport: "basketball", competitionId: "comp:nba", competitionHe: "NBA", home: team("team:a", 100), away: team("team:b", 90),
  winner: "home", leaders: [], chosenPlayerLines: [], relevanceReason: "", detailAvailable: true, ...more });
const fol = (...ids) => new Set(ids.map(i => `team:${i}`));

describe("followedTeamIds", () => {
  const aff = (target_id, level, source = "explicit", scope = "team") => ({ scope, target_id, level, source });
  it("reads team follows (level 1+) from the profile affinities, ignoring sports, players and negative levels", () => {
    const profile = { profileV2: { scope_affinities: [aff("team:x", 1), aff("team:y", 2), aff("team:z", 0), aff("team:n", -2),
      aff("player:deni_avdija", 2, "explicit", "player"), aff("basketball", 1, "explicit", "sport")] } };
    expect([...followedTeamIds(profile, [])].sort()).toEqual(["team:x", "team:y"]);
  });
  it("lets an explicit entry beat a learned one for the same target, as the backend does", () => {
    const profile = { profileV2: { scope_affinities: [aff("team:x", 2, "explicit"), aff("team:x", -2, "learned")] } };
    expect(followedTeamIds(profile, []).has("team:x")).toBe(true);
    const muted = { profileV2: { scope_affinities: [aff("team:x", 2, "learned"), aff("team:x", -2, "explicit")] } };
    expect(followedTeamIds(muted, []).has("team:x")).toBe(false);
  });
  it("also trusts the server's followed_team reason, but not a player-derived or competition reason", () => {
    const games = [game("a", "2026-11-14", { relevanceReason: "followed_team:team:m" }),
      game("b", "2026-11-14", { relevanceReason: "followed_player_team:player:deni_avdija:team:portland_blazers" }),
      game("c", "2026-11-14", { relevanceReason: "followed_competition:comp:nba" })];
    expect([...followedTeamIds(null, games)]).toEqual(["team:m"]);
  });
});

describe("tileVerdict", () => {
  it("is a win, loss or draw from the followed side's point of view", () => {
    const f = fol("a");
    expect(tileVerdict(game("1", "2026-11-14"), f)).toEqual({ kind: "win", label: "ניצחון" });
    expect(tileVerdict(game("2", "2026-11-14", { winner: "away" }), f)).toEqual({ kind: "loss", label: "הפסד" });
    expect(tileVerdict(game("3", "2026-11-14", { winner: "draw" }), f)).toEqual({ kind: "draw", label: "תיקו" });
    expect(tileVerdict(game("4", "2026-11-14", { winner: "away" }), fol("b")).kind).toBe("win");
  });
  it("has no verdict when both sides are followed or when no side can be identified", () => {
    expect(tileVerdict(game("1", "2026-11-14"), fol("a", "b"))).toBeNull();
    expect(tileVerdict(game("2", "2026-11-14"), fol("zzz"))).toBeNull();
  });
  it("uses the chosen player's side when no team is followed", () => {
    const g = game("1", "2026-11-14", { winner: "away", chosenPlayerLines: [{ side: "away", name: "דני אבדיה" }] });
    expect(tileVerdict(g, new Set()).kind).toBe("win");
    const split = { ...g, chosenPlayerLines: [{ side: "away" }, { side: "home" }] };
    expect(tileVerdict(split, new Set())).toBeNull();
  });
});

describe("tileEntries", () => {
  it("takes the four most recent finals with a followed team or a chosen-player line, never inventing tiles", () => {
    const games = [
      game("old", "2026-11-01", { home: team("team:m", 1) }),
      game("m1", "2026-11-12", { home: team("team:m", 80) }),
      game("other", "2026-11-14"),
      game("deni", "2026-11-14", { time: "03:00:00", chosenPlayerLines: [{ side: "away", name: "דני אבדיה", stats: {} }] }),
      game("m2", "2026-11-13", { away: team("team:m", 70) }),
      game("sched", "2026-11-15", { status: "scheduled", home: team("team:m", null) }),
      game("m3", "2026-11-10", { home: team("team:m", 70) }),
    ];
    const tiles = tileEntries(games, fol("m"));
    expect(tiles.map(t => t.game.id)).toEqual(["deni", "m2", "m1", "m3"]);
    expect(tiles[0].chosen.name).toBe("דני אבדיה");
    expect(tileEntries([game("x", "2026-11-14")], fol("m"))).toEqual([]);
    expect(tileEntries([], fol("m"))).toEqual([]);
  });
});

describe("leadersText", () => {
  const leaders = [{ side: "away", name: "דני אבדיה", value: 34 }, { side: "home", name: "De'Andre Hunter", value: 24 },
    { side: "home", name: "Shai Gilgeous-Alexander", value: 40 }, { side: "away", name: "Jabari Smith Jr.", value: 9 }];
  it("lists home leaders first, English names by surname and Hebrew names in full", () => {
    expect(leadersText({ leaders })).toBe("Hunter 24 · Gilgeous-Alexander 40 · דני אבדיה 34 · Smith 9");
  });
  it("is empty without leaders and skips nameless leaders", () => {
    expect(leadersText({ leaders: [] })).toBe("");
    expect(leadersText({ leaders: [{ side: "home", name: null, value: 3 }] })).toBe("");
  });
});

describe("summaryParts", () => {
  it("counts finals of the last 48 hours and today's scheduled games, dropping a zero part", () => {
    const games = [game("a", "2026-11-14"), game("b", "2026-11-13", { startTime: "2026-11-13T11:00:00Z" }),
      game("c", "2026-11-15", { status: "scheduled", startTime: "2026-11-15T18:00:00Z" })];
    expect(summaryParts(games, now)).toEqual([{ n: 1, label: "משחק ב-48 השעות האחרונות" }, { n: 1, label: "הערב" }]);
    expect(summaryParts([games[0], { ...games[0], id: "z" }], now)).toEqual([{ n: 2, label: "משחקים ב-48 השעות האחרונות" }]);
    expect(summaryParts([games[2]], now)).toEqual([{ n: 1, label: "הערב" }]);
    expect(summaryParts([], now)).toEqual([]);
  });
});

describe("collapseLeague", () => {
  const league = n => Array.from({ length: n }, (_, i) => game(`g${i}`, "2026-11-14", { time: `${String(10 + i).padStart(2, "0")}:00:00` }));
  it("keeps up to 5 games visible", () => {
    const r = collapseLeague(league(5), new Set());
    expect(r.visible).toHaveLength(5); expect(r.hidden).toHaveLength(0);
  });
  it("shows 4 above 5, followed and chosen games first, then the existing order", () => {
    const games = league(7);
    games[5] = { ...games[5], home: team("team:m", 1) };
    games[6] = { ...games[6], chosenPlayerLines: [{ side: "home" }] };
    const r = collapseLeague(games, fol("m"));
    expect(r.visible.map(g => g.id)).toEqual(["g5", "g6", "g0", "g1"]);
    expect(r.hidden.map(g => g.id)).toEqual(["g2", "g3", "g4"]);
  });
});

describe("streamDays", () => {
  it("orders today first then past days descending, leagues in grouping order, scheduled games out of the stream", () => {
    const games = [game("old", "2026-11-12"), game("today", "2026-11-15", { status: "final", time: "02:00:00" }), game("y", "2026-11-14"),
      game("up", "2026-11-16", { status: "scheduled" }), game("tonight", "2026-11-15", { status: "scheduled", time: "18:00:00" }),
      game("el", "2026-11-14", { competitionId: "comp:euroleague", competitionHe: "יורוליג" })];
    const days = streamDays(games, new Set(), now);
    expect(days.map(d => d.dayKey)).toEqual(["2026-11-15", "2026-11-14", "2026-11-12"]);
    expect(days[0].title).toBe("היום"); expect(days[1].title).toBe("אתמול");
    expect(days[1].leagues.map(l => l.competitionId)).toEqual(["comp:euroleague", "comp:nba"]);
    const ids = days.flatMap(d => d.leagues.flatMap(l => [...l.visible, ...l.hidden])).map(g => g.id);
    expect(ids).not.toContain("tonight"); expect(ids).not.toContain("up");
  });
  it("collapses a league over the threshold and reports the hidden count", () => {
    const games = Array.from({ length: 8 }, (_, i) => game(`g${i}`, "2026-11-14"));
    const [day] = streamDays(games, new Set(), now);
    expect(day.leagues[0].visible).toHaveLength(4); expect(day.leagues[0].hidden).toHaveLength(4);
  });
});

describe("dateChips", () => {
  it("lists the stream's days: היום, אתמול, then weekday and date", () => {
    const chips = dateChips([game("a", "2026-11-15"), game("b", "2026-11-14"), game("c", "2026-11-12"),
      game("s", "2026-11-16", { status: "scheduled" })], now);
    expect(chips.map(c => c.dayKey)).toEqual(["2026-11-15", "2026-11-14", "2026-11-12"]);
    expect(chips[0].label).toBe("היום"); expect(chips[1].label).toBe("אתמול");
    expect(chips[2].label).toMatch(/12\.11/);
    expect(chips[2].label).not.toMatch(/^יום/);
  });
  it("has no chips without dated finals", () => {
    expect(dateChips([], now)).toEqual([]);
    expect(dateChips([game("a", null, { localDate: null, startTime: null })], now)).toEqual([]);
  });
});

describe("sideBoxes", () => {
  const sched = (id, date, time) => game(id, date, { status: "scheduled", time, home: team("team:a", null), away: team("team:b", null) });
  it("lists today's scheduled games by time under הערב", () => {
    const { tonight } = sideBoxes([sched("late", "2026-11-15", "19:00:00"), sched("early", "2026-11-15", "16:00:00"), sched("next", "2026-11-16", "10:00:00")], now);
    expect(tonight.title).toBe("הערב"); expect(tonight.items.map(i => i.game.id)).toEqual(["early", "late"]);
  });
  it("falls back to הקרוב with day and time, and to nothing without upcoming games", () => {
    const { tonight } = sideBoxes([sched("b", "2026-11-17", "10:00:00"), sched("a", "2026-11-16", "10:00:00"), game("fin", "2026-11-14")], now);
    expect(tonight.title).toBe("הקרוב"); expect(tonight.items.map(i => i.game.id)).toEqual(["a", "b"]);
    expect(tonight.items[0].day).toBeTruthy();
    expect(sideBoxes([game("fin", "2026-11-14")], now).tonight).toBeNull();
  });
});

describe("playerLines", () => {
  it("describes each chosen line with stats, day, score and minutes", () => {
    const g = game("n", "2026-11-14", { home: { ...team("team:sacramento_kings", 107), name: "סקרמנטו קינגס" }, away: { ...team("team:portland_blazers", 120), name: "פורטלנד בלייזרס" },
      winner: "away", chosenPlayerLines: [{ side: "away", name: "דני אבדיה", minutes: 35, stats: { points: 34, rebounds: 6, assists: 4 } }] });
    const [line] = playerLines([g, game("none", "2026-11-14")], now);
    expect(line.name).toBe("דני אבדיה");
    expect(line.stats).toBe("34 נק׳ · 6 ריב׳ · 4 אס׳");
    expect(line.day).toBe("אתמול");
    expect(line.score).toBe("פורטלנד 120–107 סקרמנטו");
    expect(line.minutes).toBe("35 דק׳");
  });
  it("is empty when no chosen lines exist", () => {
    expect(playerLines([game("a", "2026-11-14")], now)).toEqual([]);
  });
});
