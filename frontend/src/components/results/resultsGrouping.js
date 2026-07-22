// Chronological grouping/sorting for results (issue #178). Pure + unit-tested.
import { jerusalemDayKey } from "./resultsFormat";

// Newest first; games with no start time sink to the bottom.
export function sortGames(games) {
  return [...games].sort((a, b) => {
    const ta = a.startTime || "";
    const tb = b.startTime || "";
    if (ta === tb) return 0;
    if (!ta) return 1;
    if (!tb) return -1;
    return tb < ta ? -1 : 1;
  });
}

// Ordered day groups, newest day first; the undated bucket (dayKey === null)
// is always last. Within a day, games are sorted newest-first.
export function groupByDay(games) {
  const buckets = new Map();
  for (const game of games) {
    const key = jerusalemDayKey(game.startTime);
    const bucketKey = key === null ? "undated-bucket" : key;
    if (!buckets.has(bucketKey)) buckets.set(bucketKey, { dayKey: key, games: [] });
    buckets.get(bucketKey).games.push(game);
  }
  const groups = [...buckets.values()];
  groups.sort((a, b) => {
    if (a.dayKey === b.dayKey) return 0;
    if (a.dayKey === null) return 1;
    if (b.dayKey === null) return -1;
    return b.dayKey < a.dayKey ? -1 : 1;
  });
  for (const group of groups) group.games = sortGames(group.games);
  return groups;
}
