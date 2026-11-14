import { hasScore, isCompleted, statusLabel } from "@/components/results/resultsModel";
import { relativeTimeHe } from "./signalStoryModel";

export const RESULTS_STRIP_LIMIT = 10;

/** The latest dated finals from the already personalized, normalized results.
 * Sorting a filtered copy preserves the context's ordering and object identities.
 * @param {readonly any[]} games
 */
export function latestFinals(games = [], nowMs = Date.now()) {
  return games
    .filter((game) => {
      const at = game.startTime ? Date.parse(game.startTime) : NaN;
      return isCompleted(game.status) && hasScore(game) &&
        Number.isFinite(game.home.score) && Number.isFinite(game.away.score) &&
        Number.isFinite(at) && at <= nowMs;
    })
    .sort((a, b) => Date.parse(b.startTime) - Date.parse(a.startTime))
    .slice(0, RESULTS_STRIP_LIMIT);
}

/** Match ResultCard: the backend's declared winner is authoritative. */
export function resultWinner(game) {
  return isCompleted(game.status) && hasScore(game) &&
    (game.winner === "home" || game.winner === "away") ? game.winner : null;
}

/** Names and competition labels are already normalized for the results page. */
export function resultStripLabels(game, nowMs) {
  return {
    competition: game.competitionHe,
    relativeTime: relativeTimeHe(game.startTime, nowMs),
    description: `${game.home.name} ${game.home.score}, ${game.away.name} ${game.away.score}, ${statusLabel(game.status)}`,
  };
}
