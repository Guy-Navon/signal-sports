// Models for the results page, direction C (#513). Pure and unit-tested; the
// components only render what these return. The server owns relevance, names,
// leaders and chosen-player lines: nothing here invents a game, a team follow or a stat.
import { chosenLineText, groupResults } from "./resultsPageModel";
import { formatDayChip, formatDayLong, formatGameTime, formatWeekday, jerusalemDayKey } from "./resultsFormat";
import { shortTeamName } from "./resultsTeamNames";

export const COLLAPSE_OVER = 5;
export const COLLAPSE_SHOW = 4;
export const TILE_LIMIT = 4;
const SOURCE_AUTHORITY = { explicit: 3, learned: 2, calibration: 1 };
const FOLLOW_THRESHOLD = 1;
const WINDOW_MS = 48 * 60 * 60 * 1000;
const SIDES = ["home", "away"];
const number = (n) => new Intl.NumberFormat("he-IL", { maximumFractionDigits: 1 }).format(n);
const dayOf = (game) => game.localDate || jerusalemDayKey(game.startTime);
const finals = (games) => (games || []).filter(g => g.status === "final");
const byStart = (a, b) => (Date.parse(b.startTime) || 0) - (Date.parse(a.startTime) || 0) || a.id.localeCompare(b.id);

// Teams the user follows directly. Mirrors the backend: team affinities of level 1+
// from the profile (an explicit entry beats a calibrated one beats a learned one, the
// later of equals wins), plus any team the server itself reported as `followed_team`.
// A team that is only in scope through a followed player is not a followed team.
export function followedTeamIds(profile, games) {
  const effective = new Map();
  for (const aff of profile?.profileV2?.scope_affinities ?? []) {
    if (aff.scope !== "team") continue;
    const existing = effective.get(aff.target_id);
    if (!existing || (SOURCE_AUTHORITY[aff.source] ?? 0) >= (SOURCE_AUTHORITY[existing.source] ?? 0)) effective.set(aff.target_id, aff);
  }
  const ids = new Set([...effective.values()].filter(a => a.level >= FOLLOW_THRESHOLD).map(a => a.target_id));
  for (const game of games || []) {
    const match = /^followed_team:(team:.+)$/.exec(game.relevanceReason || "");
    if (match) ids.add(match[1]);
  }
  return ids;
}

const isFollowedGame = (game, followed) => followed.has(game.home?.id) || followed.has(game.away?.id);
const isPriorityGame = (game, followed) => isFollowedGame(game, followed) || (game.chosenPlayerLines || []).length > 0;

function winnerSide(game) {
  if (game.winner) return game.winner;
  if (game.home?.isWinner) return "home";
  if (game.away?.isWinner) return "away";
  return null;
}

// Win / loss / draw from the followed team's side. Both sides followed, or no
// identifiable side, gives no verdict. With no followed team, a chosen player's side.
export function tileVerdict(game, followed) {
  const sides = SIDES.filter(side => followed.has(game[side]?.id));
  let mine = sides.length === 1 ? sides[0] : null;
  if (!sides.length) {
    const chosen = new Set((game.chosenPlayerLines || []).map(p => p.side));
    if (chosen.size === 1) [mine] = [...chosen];
  }
  if (!mine) return null;
  const winner = winnerSide(game);
  if (winner === "draw") return { kind: "draw", label: "תיקו" };
  if (winner === mine) return { kind: "win", label: "ניצחון" };
  if (winner) return { kind: "loss", label: "הפסד" };
  return null;
}

// The most recent finals involving a followed team or carrying a chosen-player line.
export function tileEntries(games, followed, limit = TILE_LIMIT) {
  return finals(games).filter(g => isPriorityGame(g, followed)).sort(byStart).slice(0, limit)
    .map(game => ({ game, verdict: tileVerdict(game, followed), chosen: (game.chosenPlayerLines || [])[0] || null }));
}

const HEBREW = /[֐-׿]/;
const SUFFIXES = new Set(["jr", "jr.", "sr", "sr.", "ii", "iii", "iv"]);
function leaderName(name) {
  const text = String(name || "").trim();
  if (!text || HEBREW.test(text)) return text;
  const parts = text.split(/\s+/);
  while (parts.length > 1 && SUFFIXES.has(parts[parts.length - 1].toLowerCase())) parts.pop();
  return parts[parts.length - 1];
}

// "Hunter 24 · דני אבדיה 34": home leaders first; an English name shows only the
// surname, a mapped Hebrew name shows in full.
export function leadersText(game) {
  const leaders = game.leaders || [];
  return [...leaders.filter(p => p.side === "home"), ...leaders.filter(p => p.side !== "home")]
    .map(p => ({ name: leaderName(p.name), value: p.value })).filter(p => p.name)
    .map(p => p.value == null ? p.name : `${p.name} ${p.value}`).join(" · ");
}

// Summary line parts: finals of the last 48 hours and today's scheduled games.
export function summaryParts(games, now = new Date()) {
  const today = jerusalemDayKey(now.toISOString());
  const since = now.getTime() - WINDOW_MS;
  const recent = finals(games).filter(g => { const t = Date.parse(g.startTime); return t > since && t <= now.getTime(); }).length;
  const tonight = (games || []).filter(g => g.status === "scheduled" && dayOf(g) === today).length;
  const parts = [];
  if (recent) parts.push({ n: recent, label: recent === 1 ? "משחק ב-48 השעות האחרונות" : "משחקים ב-48 השעות האחרונות" });
  if (tonight) parts.push({ n: tonight, label: "הערב" });
  return parts;
}

// A league with more than five games on one day shows four: followed and chosen
// games first, then the existing order.
export function collapseLeague(games, followed) {
  if (games.length <= COLLAPSE_OVER) return { visible: games, hidden: [] };
  const ordered = [...games.filter(g => isPriorityGame(g, followed)), ...games.filter(g => !isPriorityGame(g, followed))];
  return { visible: ordered.slice(0, COLLAPSE_SHOW), hidden: ordered.slice(COLLAPSE_SHOW) };
}

function dayTitle(dayKey, now) {
  if (!dayKey) return { title: "ללא תאריך", sub: "" };
  const today = jerusalemDayKey(now.toISOString());
  const yesterday = jerusalemDayKey(new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString());
  if (dayKey === today) return { title: "היום", sub: formatDayLong(dayKey) };
  if (dayKey === yesterday) return { title: "אתמול", sub: formatDayLong(dayKey) };
  return { title: formatWeekday(dayKey), sub: formatDayLong(dayKey).replace(/^[^,]+,\s*/, "") };
}

function pastDays(games, now) {
  return groupResults(finals(games), now);
}

// Day sections, today first then past days descending. Scheduled games stay out of
// the stream: they live in the tonight box. Leagues keep the grouping order.
export function streamDays(games, followed, now = new Date()) {
  return pastDays(games, now).map(day => ({
    dayKey: day.dayKey, ...dayTitle(day.dayKey, now),
    leagues: day.sports.flatMap(sport => sport.leagues).map(league => ({
      competitionId: league.competitionId, label: league.label, ...collapseLeague(league.games, followed),
    })),
  }));
}

export function dateChips(games, now = new Date()) {
  const today = jerusalemDayKey(now.toISOString());
  const yesterday = jerusalemDayKey(new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString());
  return pastDays(games, now).filter(d => d.dayKey).map(d => ({ dayKey: d.dayKey,
    label: d.dayKey === today ? "היום" : d.dayKey === yesterday ? "אתמול" : formatDayChip(d.dayKey) }));
}

// "הערב": today's scheduled games. With none, "הקרוב": the next upcoming games with
// day and time. Nothing upcoming means no box.
export function sideBoxes(games, now = new Date()) {
  const today = jerusalemDayKey(now.toISOString());
  const scheduled = (games || []).filter(g => g.status === "scheduled" && dayOf(g))
    .sort((a, b) => (Date.parse(a.startTime) || 0) - (Date.parse(b.startTime) || 0) || a.id.localeCompare(b.id));
  const tonight = scheduled.filter(g => dayOf(g) === today);
  const upcoming = scheduled.filter(g => dayOf(g) > today).slice(0, 5);
  const entry = (game) => ({ game, time: formatGameTime(game.startTime), day: dayTitle(dayOf(game), now).title });
  if (tonight.length) return { tonight: { title: "הערב", items: tonight.map(entry) } };
  if (upcoming.length) return { tonight: { title: "הקרוב", items: upcoming.map(entry) } };
  return { tonight: null };
}

// Each chosen-player line in the window: stats, then day, score and minutes.
export function playerLines(games, now = new Date()) {
  return finals(games).sort(byStart).flatMap(game => (game.chosenPlayerLines || []).map((line, i) => {
    const mine = line.side === "away" ? "away" : "home", other = mine === "home" ? "away" : "home";
    const scored = game[mine]?.score != null && game[other]?.score != null;
    return {
      key: `${game.id}-${line.entity_id || line.name}-${i}`, gameId: game.id, name: line.name,
      stats: chosenLineText({ stats: line.stats }, game.sport),
      day: dayTitle(dayOf(game), now).title,
      score: scored ? `${shortTeamName(game[mine])} ${game[mine].score}–${game[other].score} ${shortTeamName(game[other])}` : "",
      minutes: line.minutes != null ? `${number(line.minutes)} דק׳` : "",
    };
  }));
}
