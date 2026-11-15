import { jerusalemDayKey } from "./resultsFormat";

export const SPORT_LABELS = { basketball: "כדורסל", football: "כדורגל", tennis: "טניס" };
const SPORT_ORDER = ["basketball", "football", "tennis"];
const number = (n) => new Intl.NumberFormat("he-IL", { maximumFractionDigits: 1 }).format(n);

export function pageState({ loading = false, error = null, hasPreferences = false, games = [] } = {}) {
  if (loading && !games.length) return "loading";
  if (error) return "error";
  if (!hasPreferences) return "preferences";
  return games.some(g => g.status === "final" || g.status === "scheduled") ? "ready" : "empty";
}

function dateOrder(a, b, today) {
  if (a === b) return 0;
  if (!a) return 1; if (!b) return -1;
  const bucket = (key) => key === today ? 0 : key > today ? 1 : 2;
  if (bucket(a) !== bucket(b)) return bucket(a) - bucket(b);
  return a > today ? a.localeCompare(b) : b.localeCompare(a);
}

export function groupResults(games, now = new Date()) {
  const today = jerusalemDayKey(now.toISOString());
  const days = new Map();
  for (const game of games || []) {
    if (game.status !== "final" && game.status !== "scheduled") continue;
    const dayKey = game.localDate || jerusalemDayKey(game.startTime);
    if (!days.has(dayKey)) days.set(dayKey, { dayKey, sports: new Map() });
    const day = days.get(dayKey);
    if (!day.sports.has(game.sport)) day.sports.set(game.sport, { sport: game.sport, leagues: new Map() });
    const sport = day.sports.get(game.sport);
    if (!sport.leagues.has(game.competitionId)) sport.leagues.set(game.competitionId, {
      competitionId: game.competitionId, label: game.competitionHe, games: [],
    });
    sport.leagues.get(game.competitionId).games.push(game);
  }
  return [...days.values()].sort((a, b) => dateOrder(a.dayKey, b.dayKey, today)).map(day => ({
    dayKey: day.dayKey,
    sports: [...day.sports.values()].sort((a, b) => {
      const rank = sport => SPORT_ORDER.includes(sport) ? SPORT_ORDER.indexOf(sport) : 99;
      return rank(a.sport) - rank(b.sport) || a.sport.localeCompare(b.sport);
    }).map(sport => ({ sport: sport.sport,
      leagues: [...sport.leagues.values()].sort((a, b) => a.competitionId.localeCompare(b.competitionId)).map(league => ({
        ...league, games: [...league.games].sort((a, b) => {
          if (a.status !== b.status) return a.status === "final" ? -1 : 1;
          const ta = Date.parse(a.startTime), tb = Date.parse(b.startTime);
          if (!Number.isFinite(ta)) return Number.isFinite(tb) ? 1 : a.id.localeCompare(b.id);
          if (!Number.isFinite(tb)) return -1;
          return (a.status === "scheduled" ? ta - tb : tb - ta) || a.id.localeCompare(b.id);
        }),
      })),
    })),
  }));
}

export function chosenLineText(line, sport) {
  const labels = sport === "football" ? { goals: "שערים", assists: "בישולים", yellow_cards: "צהובים", red_cards: "אדומים" }
    : { points: "נק׳", rebounds: "ריב׳", assists: "אס׳" };
  const parts = Object.entries(labels).filter(([key]) => line.stats?.[key] != null)
    .map(([key, label]) => `${number(line.stats[key])} ${label}`);
  if (line.minutes != null) parts.push(`${number(line.minutes)} דק׳`);
  return parts.join(" · ");
}

const STAT_LABELS = { points: "נקודות", Points: "נקודות", rebounds: "ריבאונדים", TotalRebounds: "ריבאונדים", assists: "אסיסטים", Assistances: "אסיסטים",
  goals: "שערים", yellow_cards: "צהובים", red_cards: "אדומים", own_goals: "שערים עצמיים", minutes: "דקות", coach: "מאמן", rank: "דירוג",
  quarters: "רבעים", quarter_scores: "רבעים", q1: "רבע 1", q2: "רבע 2", q3: "רבע 3", q4: "רבע 4", Q1: "רבע 1", Q2: "רבע 2", Q3: "רבע 3", Q4: "רבע 4",
  steals: "חטיפות", Steals: "חטיפות", turnovers: "איבודים", Turnovers: "איבודים", blocks: "חסימות", BlocksFavour: "חסימות", fouls: "עבירות", FoulsCommited: "עבירות",
  OffensiveRebounds: "ריבאונד התקפה", DefensiveRebounds: "ריבאונד הגנה", Plusminus: "פלוס/מינוס", Valuation: "מדד", xg: "שערים צפויים", attendance: "קהל" };
export const statLabel = key => STAT_LABELS[key] || key.replace(/([a-z])([A-Z])/g, "$1 $2").replaceAll("_", " ");

export function teamStatEntries(stats, prefix = "", depth = 0) {
  return Object.entries(stats || {}).flatMap(([key, value]) => {
    if (value == null || typeof value === "boolean" || key === "standings_round") return [];
    const label = [prefix, statLabel(key)].filter(Boolean).join(" · ");
    if (typeof value === "object") return depth < 2 ? teamStatEntries(value, label, depth + 1) : [];
    return [[label, value]];
  });
}
