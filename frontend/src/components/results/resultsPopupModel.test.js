import { describe, expect, it } from "vitest";
import { boxScore, footballEvents, periodTable, popupHeader, scoreboard, teamFacts } from "./resultsPopupModel";
import fixture from "../../lab/resultsFixtures.json";

const game = (id) => {
  const g = fixture.games.find(x => x.id === id);
  return { id: g.id, sport: g.sport, competitionHe: g.competition_he, startTime: g.start_time, localDate: g.local_date, status: g.status,
    home: { ...g.home, isWinner: g.home.is_winner }, away: { ...g.away, isWinner: g.away.is_winner }, winner: g.winner,
    leaders: g.leaders, chosenPlayerLines: g.chosen_player_lines };
};
const byComp = (c) => fixture.games.find(g => g.competition_id === c && g.status === "final").id;
const ibl = byComp("comp:ibl"), el = byComp("comp:euroleague"), nba = byComp("comp:nba"), fc = byComp("comp:ligat_haal");

describe("periodTable", () => {
  it("reads quarter_scores arrays, numbered from 1, with the game's totals", () => {
    const t = periodTable(fixture.details[ibl], game(ibl));
    expect(t.labels).toEqual(["1", "2", "3", "4"]);
    expect(t.rows.map(r => r.values)).toEqual([[22, 25, 16, 24], [26, 33, 24, 22]]);
    expect(t.rows.map(r => r.total)).toEqual([87, 105]);
  });
  it("reads provider quarters given as an object or as an array", () => {
    expect(periodTable(fixture.details[el], game(el)).rows[0].values).toEqual([25, 16, 15, 24]);
    expect(periodTable(fixture.details[nba], game(nba)).rows[1].values).toEqual([34, 30, 29, 27]);
  });
  it("labels overtime periods and shows nothing without periods for both sides", () => {
    const ot = periodTable({ team_stats: { home: { quarter_scores: [20, 20, 20, 20, 9] }, away: { quarter_scores: [20, 20, 20, 20, 8] } } }, game(ibl));
    expect(ot.labels).toEqual(["1", "2", "3", "4", "הארכה"]);
    expect(periodTable({ team_stats: { home: { quarter_scores: [1, 2] }, away: {} } }, game(ibl))).toBeNull();
    expect(periodTable(fixture.details[fc], game(fc))).toBeNull();
    expect(periodTable(null, game(ibl))).toBeNull();
  });
});

describe("teamFacts", () => {
  it("picks up to four comparisons the provider has, in a fixed order", () => {
    const facts = teamFacts(fixture.details[ibl], "basketball");
    expect(facts.map(f => f.label)).toEqual(["נקודות מהספסל", "נקודות בצבע", "יתרון שיא", "חילופי יתרון"]);
    expect(facts[0]).toMatchObject({ home: 32, away: 49 });
  });
  it("understands the ESPN spellings and numeric strings", () => {
    const facts = teamFacts(fixture.details[nba], "basketball");
    expect(facts.find(f => f.label === "נקודות בצבע")).toMatchObject({ home: 46 });
    expect(facts.find(f => f.label === "יתרון שיא").home).toBe(5);
    expect(facts.length).toBeLessThanOrEqual(4);
  });
  it("skips facts a provider lacks, shows none when there are none, and none for football", () => {
    expect(teamFacts(fixture.details[el], "basketball")).toEqual([]);
    expect(teamFacts({ team_stats: { home: { bench_points: 10 }, away: { bench_points: null } } }, "basketball")).toEqual([]);
    expect(teamFacts(fixture.details[fc], "football")).toEqual([]);
    expect(teamFacts(null, "basketball")).toEqual([]);
  });
});

describe("boxScore", () => {
  it("groups starters and bench and shows only the columns the data has (winner)", () => {
    const box = boxScore(fixture.details[ibl], "home", "basketball");
    expect(box.columns).toEqual(["min", "pts", "reb", "ast", "fg2", "fg3", "ft", "pm"]);
    const all = box.groups.flatMap(g => g.rows);
    expect(box.groups.map(g => g.key)).toEqual(["starters", "bench"]);
    expect(box.groups[0].rows.length).toBe(5);
    const hoard = all.find(r => r.name === "ג'יילן הורד");
    expect(hoard).toMatchObject({ pts: 4, reb: 9, ast: 0, fg2: "2/6", fg3: "0/0", ft: "0/0", pm: -13, min: 22 });
  });
  it("derives made/attempted for EuroLeague and subtracts threes from ESPN field goals", () => {
    const hoard = boxScore(fixture.details[el], "home", "basketball").groups.flatMap(g => g.rows).find(r => r.name === "ג'יילן הורד");
    expect(hoard).toMatchObject({ pts: 8, fg2: "4/5", fg3: "0/1", ft: "0/0", pm: 10 });
    const camara = boxScore(fixture.details[nba], "away", "basketball").groups.flatMap(g => g.rows).find(r => r.name === "Toumani Camara");
    expect(camara).toMatchObject({ pts: 14, reb: 2, ast: 1, fg2: "3/3", fg3: "2/4", ft: "2/2", pm: 9, min: 36 });
  });
  it("marks the top scorer once, with a tie going to the first, and nobody when nobody scored", () => {
    const rows = boxScore(fixture.details[nba], "away", "basketball").groups.flatMap(g => g.rows);
    expect(rows.filter(r => r.top)).toHaveLength(1);
    expect(rows.find(r => r.top).name).toBe("דני אבדיה");
    const none = boxScore({ players: [{ side: "home", name: "A", minutes: 5, stats: { points: 0, starter: true } }] }, "home", "basketball");
    expect(none.groups.flatMap(g => g.rows).some(r => r.top)).toBe(false);
  });
  it("omits a column no player has and players who did not play", () => {
    const detail = { players: [{ side: "home", name: "A", minutes: 10, stats: { points: 2, starter: true } },
      { side: "home", name: "B", minutes: null, stats: { points: 0 } }, { side: "away", name: "C", minutes: 3, stats: { points: 1 } }] };
    const box = boxScore(detail, "home", "basketball");
    expect(box.columns).toEqual(["min", "pts"]);
    expect(box.groups.flatMap(g => g.rows).map(r => r.name)).toEqual(["A"]);
  });
  it("returns an empty box for no players", () => {
    expect(boxScore({ players: [] }, "home", "basketball").groups).toEqual([]);
    expect(boxScore(null, "home", "basketball").groups).toEqual([]);
  });
});

describe("footballEvents", () => {
  it("lists named scorers and cards per side and skips unnamed players", () => {
    const detail = { players: [{ side: "home", name: "אסטר סוקלר", stats: { goals: 1, yellow_cards: 0 } },
      { side: "home", name: null, stats: { goals: 1 } }, { side: "away", name: "איתן טיבי", stats: { goals: 2, yellow_cards: 1, red_cards: 0 } },
      { side: "away", name: "מישהו", stats: { goals: 0, yellow_cards: 0 } }] };
    expect(footballEvents(detail)).toEqual({
      home: [{ name: "אסטר סוקלר", goals: 1, yellow: 0, red: 0 }],
      away: [{ name: "איתן טיבי", goals: 2, yellow: 1, red: 0 }],
    });
    expect(footballEvents(null)).toEqual({ home: [], away: [] });
  });
});

describe("scoreboard and header", () => {
  it("shows full names, the top scorer of each side and the winner", () => {
    const board = scoreboard(game(nba));
    expect(board.away.name).toBe("פורטלנד בלייזרס");
    expect(board.away.top).toBe("דני אבדיה 34");
    expect(board.home.top).toBe("De'Andre Hunter 24");
    expect(board.winner).toBe("away");
  });
  it("describes the header as league, date, time and venue with attendance", () => {
    const text = popupHeader(game(ibl), fixture.details[ibl]);
    expect(text).toContain("ליגת ווינר סל");
    expect(text).toContain("1 בנובמבר");
    expect(text).toMatch(/20:55/);
    expect(text).toContain("היכל מנורה מבטחים");
    expect(text).toContain("8,314");
    expect(popupHeader(game(ibl), null)).not.toContain("היכל");
  });
});
