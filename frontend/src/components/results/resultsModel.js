// Results domain helpers (issue #178) — pure, framework-free, unit-tested.

export const RESULT_STATUS = {
  SCHEDULED: "scheduled",
  LIVE: "live",
  FINAL: "final",
  POSTPONED: "postponed",
  CANCELLED: "cancelled",
  UNKNOWN: "unknown",
};

// A completed game whose score is meaningful.
export const COMPLETED_STATUSES = new Set([RESULT_STATUS.FINAL]);

// Hebrew status labels for the status chip.
const STATUS_LABELS = {
  [RESULT_STATUS.FINAL]: "תוצאה סופית",
  [RESULT_STATUS.LIVE]: "משחק חי",
  [RESULT_STATUS.SCHEDULED]: "עתידי",
  [RESULT_STATUS.POSTPONED]: "נדחה",
  [RESULT_STATUS.CANCELLED]: "בוטל",
  [RESULT_STATUS.UNKNOWN]: "",
};

export function statusLabel(status) {
  return STATUS_LABELS[status] ?? "";
}

export function isCompleted(status) {
  return COMPLETED_STATUSES.has(status);
}

export function hasScore(game) {
  return (
    game?.home?.score !== null &&
    game?.home?.score !== undefined &&
    game?.away?.score !== null &&
    game?.away?.score !== undefined
  );
}

// Normalize the API GameResult (snake_case) to the camelCase shape the UI uses.
export function normalizeResultFromApi(raw) {
  const side = (s) => ({
    id: s?.id ?? null,
    name: s?.name ?? s?.name_provider ?? "",
    nameProvider: s?.name_provider ?? s?.name ?? "",
    score: s?.score ?? null,
    isWinner: Boolean(s?.is_winner),
  });
  return {
    id: raw.id,
    competitionId: raw.competition_id,
    competitionHe: raw.competition_he ?? raw.competition_id,
    competitionEn: raw.competition_en ?? raw.competition_id,
    sport: raw.sport,
    season: raw.season ?? null,
    stage: raw.stage ?? null,
    status: raw.status ?? RESULT_STATUS.UNKNOWN,
    startTime: raw.start_time ?? null,
    home: side(raw.home),
    away: side(raw.away),
    winner: raw.winner ?? null,
    relevanceReason: raw.relevance_reason ?? "",
  };
}

export function normalizeResultsResponse(raw) {
  return {
    hasPreferences: Boolean(raw?.has_preferences),
    games: Array.isArray(raw?.games) ? raw.games.map(normalizeResultFromApi) : [],
  };
}
