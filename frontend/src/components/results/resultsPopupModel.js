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

function shooting(stats) {
  const made = (a, b) => num(stats[a]) != null && num(stats[b]) != null ? [num(stats[a]), num(stats[a]) + num(stats[b])] : null;
  const att = (m, a) => num(stats[m]) != null && num(stats[a]) != null ? [num(stats[m]), num(stats[a])] : null;
  let two = made("fg2_made", "fg2_missed") || att("FieldGoalsMade2", "FieldGoalsAttempted2");
  let three = made("fg3_made", "fg3_missed") || att("FieldGoalsMade3", "FieldGoalsAttempted3");
  let ft = made("ft_made", "ft_missed") || att("FreeThrowsMade", "FreeThrowsAttempted");
  if (!two && !three && stats.FG != null) {
    // ESPN gives total field goals and threes; the two-point line is the difference.
    const total = splitShot(stats.FG), threes = splitShot(stats["3PT"]);
    three = threes;
    if (total && threes) two = [total[0] - threes[0], total[1] - threes[1]];
  }
  if (!ft && stats.FT != null) ft = splitShot(stats.FT);
  return { fg2: two && pair(...two), fg3: three && pair(...three), ft: ft && pair(...ft) };
}

function playerRow(p, i) {
  const s = p.stats || {};
  const minutes = num(p.minutes);
  return {
    key: p.source_player_id || p.entity_id || `${p.name}-${i}`, name: p.name || "שחקן לא מזוהה",
    min: minutes == null ? null : Math.round(minutes),
    pts: first(s, ["points", "Points", "PTS"]), reb: first(s, ["rebounds", "TotalRebounds", "REB"]),
    ast: first(s, ["assists", "Assistances", "AST"]), pm: first(s, ["plus_minus", "Plusminus", "+/-"]),
    ...shooting(s), starter: Boolean(s.starter ?? s.IsStarter),
  };
}

const played = (row) => (row.min != null && row.min > 0) || (row.pts != null && row.pts > 0);
export const BOX_COLUMNS = ["min", "pts", "reb", "ast", "fg2", "fg3", "ft", "pm"];

// The box score of one side: starters then bench, only the columns the data has,
// and the top scorer flagged.
export function boxScore(detail, side, sport) {
  if (sport !== "basketball") return { columns: [], groups: [] };
  const rows = (detail?.players || []).filter(p => p.side === side).map(playerRow).filter(played);
  const columns = BOX_COLUMNS.filter(col => rows.some(r => r[col] != null));
  const top = rows.reduce((best, r) => r.pts != null && r.pts > 0 && (!best || r.pts > best.pts) ? r : best, null);
  const marked = rows.map(r => ({ ...r, top: r === top }));
  const hasStarters = marked.some(r => r.starter);
  const groups = hasStarters ? [{ key: "starters", label: "חמישייה", rows: marked.filter(r => r.starter) },
    { key: "bench", label: "ספסל", rows: marked.filter(r => !r.starter) }] : [{ key: "players", label: "", rows: marked }];
  return { columns, groups: groups.filter(g => g.rows.length) };
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
