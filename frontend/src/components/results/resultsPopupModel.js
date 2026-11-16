// Models for the game popup (#513). Pure and unit-tested. Providers spell the same
// stat differently (Winner, EuroLeague, ESPN); this reads each spelling, skips what a
// provider lacks, and never invents a value or a column.
import { formatDayLong, formatGameTime, jerusalemDayKey } from "./resultsFormat";

const SIDES = ["home", "away"];
const num = (v) => {
  if (v == null || v === "" || typeof v === "boolean") return null;
  const n = typeof v === "number" ? v : Number(String(v).replace(/^\+/, ""));
  return Number.isFinite(n) ? n : null;
};
const first = (obj, keys) => {
  for (const key of keys) { const n = num(obj?.[key]); if (n != null) return n; }
  return null;
};

function periodValues(stats) {
  const raw = stats?.quarter_scores ?? stats?.quarters;
  if (Array.isArray(raw)) return raw.map(num);
  if (raw && typeof raw === "object") {
    return Object.entries(raw).filter(([key]) => /(\d+)$/.test(key))
      .sort(([a], [b]) => Number(/(\d+)$/.exec(a)[1]) - Number(/(\d+)$/.exec(b)[1])).map(([, v]) => num(v));
  }
  return null;
}

// One row per team, one column per period plus the total. Periods are numbered
// from 1 and the fifth onward are overtime. Only when both teams have every period.
export function periodTable(detail, game) {
  const values = SIDES.map(side => periodValues(detail?.team_stats?.[side]));
  if (values.some(v => !v || !v.length || v.some(n => n == null)) || values[0].length !== values[1].length) return null;
  const labels = values[0].map((_, i) => i < 4 ? String(i + 1) : i === 4 ? "הארכה" : `הארכה ${i - 3}`);
  return { labels, rows: SIDES.map((side, i) => ({ side, name: game[side].name, values: values[i], total: game[side].score })) };
}

/** @type {Array<[string, string[]]>} */
const FACTS = [
  ["נקודות מהספסל", ["bench_points", "benchPoints"]],
  ["נקודות בצבע", ["pts_in_the_paint", "pointsInPaint"]],
  ["יתרון שיא", ["biggest_lead", "largestLead"]],
  ["חילופי יתרון", ["lead_changes", "leadChanges"]],
  ["נקודות במתפרצת", ["fastBreakPoints"]],
  ["נקודות מאיבודים", ["pts_from_turnovers", "turnoverPoints"]],
  ["נקודות מהזדמנות שנייה", ["second_chance_pts"]],
];

// Up to four team comparisons the provider actually has, for both teams.
export function teamFacts(detail, sport) {
  if (sport !== "basketball") return [];
  const stats = detail?.team_stats || {};
  return FACTS.flatMap(([label, keys]) => {
    const [home, away] = SIDES.map(side => first(stats[side], keys));
    return home == null || away == null ? [] : [{ label, home, away }];
  }).slice(0, 4);
}

const pair = (made, att) => made == null || att == null ? null : `${made}/${att}`;
const splitShot = (value) => {
  const m = /^(\d+)\s*[-/]\s*(\d+)$/.exec(String(value ?? "").trim());
  return m ? [Number(m[1]), Number(m[2])] : null;
};

function shotLines(stats) {
  const made = (a, b) => num(stats[a]) != null && num(stats[b]) != null ? [num(stats[a]), num(stats[a]) + num(stats[b])] : null;
  const att = (m, a) => num(stats[m]) != null && num(stats[a]) != null ? [num(stats[m]), num(stats[a])] : null;
  let two = made("fg2_made", "fg2_missed") || att("FieldGoalsMade2", "FieldGoalsAttempted2");
  let three = made("fg3_made", "fg3_missed") || att("FieldGoalsMade3", "FieldGoalsAttempted3");
  let ft = made("ft_made", "ft_missed") || att("FreeThrowsMade", "FreeThrowsAttempted");
  const valid = p => p && p.every(n => n >= 0) && p[0] <= p[1] ? p : null;
  three ||= splitShot(stats["3PT"] ?? stats["threePointFieldGoalsMade-threePointFieldGoalsAttempted"]);
  ft ||= splitShot(stats.FT ?? stats["freeThrowsMade-freeThrowsAttempted"]);
  let fg = splitShot(stats.FG ?? stats["fieldGoalsMade-fieldGoalsAttempted"]);
  if (!two && fg && three) two = valid([fg[0] - three[0], fg[1] - three[1]]);
  if (!fg && two && three) fg = [two[0] + three[0], two[1] + three[1]];
  return { fg: valid(fg), fg2: valid(two), fg3: valid(three), ft: valid(ft) };
}

const percent = shot => shot?.[1] > 0 ? Math.round(shot[0] / shot[1] * 1000) / 10 : null;
const percentText = shot => percent(shot) == null ? null : `${percent(shot)}%`;
const STAT_KEYS = {
  pts: ["points", "Points", "PTS"], reb: ["rebounds", "TotalRebounds", "REB", "totalRebounds"],
  ast: ["assists", "Assistances", "AST"], stl: ["steals", "Steals", "STL"],
  blk: ["blocks", "BlocksFavour", "BLK"], tov: ["totalTurnovers", "turnovers", "Turnovers", "TO"],
  pf: ["fouls", "FoulsCommited", "PF"], oreb: ["rebounds_offensive", "OffensiveRebounds", "OREB", "offensiveRebounds"],
  dreb: ["rebounds_defensive", "DefensiveRebounds", "DREB", "defensiveRebounds"],
  pm: ["plus_minus", "Plusminus", "+/-"], rating: ["rate", "Valuation", "valuation"],
};

function playerRow(p, i) {
  const s = p.stats || {};
  const minutes = num(p.minutes);
  const shots = shotLines(s);
  const { pts, reb, ast, stl, blk, tov, pf, oreb, dreb, pm, rating } =
    Object.fromEntries(Object.entries(STAT_KEYS).map(([key, aliases]) => [key, first(s, aliases)]));
  return {
    key: p.source_player_id || p.entity_id || `${p.name}-${i}`, name: p.name || "שחקן לא מזוהה",
    min: minutes == null ? null : Math.round(minutes),
    pts, reb, ast, stl, blk, tov, pf, oreb, dreb, pm, rating,
    ...Object.fromEntries(Object.entries(shots).map(([key, value]) => [key, value && pair(...value)])),
    fgpct: percentText(shots.fg), fg3pct: percentText(shots.fg3), ftpct: percentText(shots.ft),
    shots, starter: Boolean(s.starter ?? s.IsStarter),
  };
}

const played = (row) => (row.min != null && row.min > 0) || ["pts", "reb", "ast", "stl", "blk"].some(key => row[key] > 0);
export const BOX_COLUMNS = ["min", "pts", "reb", "ast", "stl", "blk", "tov", "pf", "fg2", "fg3", "ft", "pm"];
export const EXPANDED_BOX_COLUMNS = ["min", "pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov", "pf",
  "fg", "fgpct", "fg2", "fg3", "fg3pct", "ft", "ftpct", "pm", "rating"];

function summedShots(rows, key) {
  if (!rows.length || rows.some(row => !row.shots[key])) return null;
  return rows.reduce((sum, row) => [sum[0] + row.shots[key][0], sum[1] + row.shots[key][1]], [0, 0]);
}

function playerTotals(rows) {
  const totals = {};
  for (const key of ["pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov", "pf"]) {
    totals[key] = rows.length && rows.every(row => row[key] != null) ? rows.reduce((sum, row) => sum + row[key], 0) : null;
  }
  for (const key of ["fg", "fg2", "fg3", "ft"]) {
    const shot = summedShots(rows, key);
    totals[key] = shot && pair(...shot);
    if (key !== "fg2") totals[`${key}pct`] = percentText(shot);
  }
  return totals;
}

// The box score of one side: starters then bench, only the columns the data has,
// and the top scorer flagged.
export function boxScore(detail, side, sport, expanded = false) {
  if (sport !== "basketball") return { columns: [], groups: [] };
  const rows = (detail?.players || []).filter(p => p.side === side).map(playerRow).filter(played);
  const columns = (expanded ? EXPANDED_BOX_COLUMNS : BOX_COLUMNS).filter(col => rows.some(r => r[col] != null));
  const top = rows.reduce((best, r) => r.pts != null && r.pts > 0 && (!best || r.pts > best.pts) ? r : best, null);
  const marked = rows.map(r => ({ ...r, top: r === top }));
  const hasStarters = marked.some(r => r.starter);
  const groups = hasStarters ? [{ key: "starters", label: "חמישייה", rows: marked.filter(r => r.starter) },
    { key: "bench", label: "ספסל", rows: marked.filter(r => !r.starter) }] : [{ key: "players", label: "", rows: marked }];
  return { columns, groups: groups.filter(g => g.rows.length), totals: playerTotals(rows) };
}

export function gameLeaders(detail, sport) {
  if (sport !== "basketball") return [];
  const rows = (detail?.players || []).map(playerRow).filter(played);
  return [["pts", "נקודות"], ["reb", "ריבאונדים"], ["ast", "אסיסטים"]].flatMap(([key, label]) => {
    const value = Math.max(0, ...rows.map(row => row[key] ?? 0));
    return value > 0 ? [{ key, label, value, names: rows.filter(row => row[key] === value).map(row => row.name).join(" · ") }] : [];
  });
}

// Prefer official team totals. Sum player lines only when their points account
// for the complete final score; an incomplete box must not become a team total.
export function teamComparison(detail, game) {
  const stats = detail?.team_stats || {};
  const rowsBySide = Object.fromEntries(SIDES.map(side => [side,
    (detail?.players || []).filter(p => p.side === side).map(playerRow).filter(played)]));
  const complete = side => rowsBySide[side].length > 0 && rowsBySide[side].every(row => row.pts != null)
    && rowsBySide[side].reduce((sum, row) => sum + row.pts, 0) === game[side]?.score;
  const count = (side, key) => {
    const official = first(stats[side], STAT_KEYS[key]);
    return official ?? (complete(side) ? playerTotals(rowsBySide[side])[key] : null);
  };
  /** @type {Array<[string, string, string[] | null]>} */
  const definitions = game.sport === "football" ? [
    ["goals", "שערים", ["goals"]], ["assists", "בישולים", ["assists"]], ["xg", "שערים צפויים", ["xg"]],
    ["yellow", "כרטיסים צהובים", ["yellow_cards"]], ["red", "כרטיסים אדומים", ["red_cards"]],
  ] : [
    ["reb", "ריבאונדים", null], ["ast", "אסיסטים", null], ["stl", "חטיפות", null], ["blk", "חסימות", null],
    ["tov", "איבודים", null], ["oreb", "ריבאונד התקפה", null], ["dreb", "ריבאונד הגנה", null], ["pf", "עבירות", null],
    ...FACTS.map(([label, keys], i) => /** @type {[string, string, string[]]} */ ([`fact-${i}`, label, keys])),
  ];
  const rows = definitions.flatMap(([key, label, aliases]) => {
    const [home, away] = SIDES.map(side => aliases ? first(stats[side], aliases) : count(side, key));
    if (home == null || away == null || home < 0 || away < 0) return [];
    return [{ key, label, home, away, lowerBetter: ["tov", "pf", "yellow", "red"].includes(key),
      homeShare: home + away > 0 ? home / (home + away) * 100 : 50 }];
  });
  const shooting = game.sport !== "basketball" ? [] : [["fg", "מהשדה"], ["fg3", "לשלוש"], ["ft", "מהעונשין"]].flatMap(([key, label]) => {
    const values = SIDES.map(side => shotLines(stats[side] || {})[key]
      || (complete(side) ? summedShots(rowsBySide[side], key) : null));
    if (values.some(value => !value)) return [];
    return [{ key, label, home: { line: pair(...values[0]), percent: percent(values[0]) },
      away: { line: pair(...values[1]), percent: percent(values[1]) } }];
  });
  return { rows, shooting };
}

// Named scorers and cards for a football game; unnamed players are skipped.
export function footballEvents(detail) {
  const out = { home: [], away: [] };
  for (const p of detail?.players || []) {
    if (!p.name || !out[p.side]) continue;
    const s = p.stats || {};
    const goals = num(s.goals) || 0, yellow = num(s.yellow_cards) || 0, red = num(s.red_cards) || 0;
    if (goals || yellow || red) out[p.side].push({ name: p.name, goals, yellow, red });
  }
  return out;
}

export function scoreboard(game) {
  const topFull = (side) => {
    const leader = (game.leaders || []).find(p => p.side === side && p.name);
    return leader ? (leader.value == null ? leader.name : `${leader.name} ${leader.value}`) : "";
  };
  const winner = game.winner || (game.home?.isWinner ? "home" : game.away?.isWinner ? "away" : null);
  return { winner, home: { name: game.home.name, score: game.home.score, top: topFull("home") },
    away: { name: game.away.name, score: game.away.score, top: topFull("away") } };
}

export function popupHeader(game, detail) {
  const day = game.localDate || jerusalemDayKey(game.startTime);
  const parts = [game.competitionHe, day && formatDayLong(day), formatGameTime(game.startTime)];
  if (detail?.venue) parts.push(detail.venue);
  if (detail?.attendance != null) parts.push(`${new Intl.NumberFormat("he-IL").format(detail.attendance)} צופים`);
  return parts.filter(Boolean).join(" · ");
}
