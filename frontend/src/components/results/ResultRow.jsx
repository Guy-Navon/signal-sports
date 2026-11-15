import React from "react";
import { leadersText } from "./resultsLayoutModel";
import { shortTeamName } from "./resultsTeamNames";
import { RESULTS_STATS_MARKER } from "./resultsStatsBoundary";

export function FollowDot() {
  return <span className="sr-dot" role="img" aria-label="קבוצה שאתה עוקב אחריה" />;
}

const winnerOf = (game) => game.status === "final" ? (game.winner ?? (game.home.isWinner ? "home" : game.away.isWinner ? "away" : null)) : null;

// One line on a desktop, two on a phone: home | score | away, then the leaders.
// The row opens the game popup when the provider has game data.
export default function ResultRow({ game, followed, onOpen, rowRef = null }) {
  const openable = game.detailAvailable;
  const Row = openable ? "button" : "div";
  const winner = winnerOf(game);
  const leaders = leadersText(game);
  const side = (key) => <span className={`sr-team sr-team--${key}`} data-winner={winner === key || undefined}>
    {followed.has(game[key].id) && key === "home" && <FollowDot />}
    <bdi dir="auto">{shortTeamName(game[key])}</bdi>
    {followed.has(game[key].id) && key === "away" && <FollowDot />}
  </span>;
  return <Row ref={rowRef} type={openable ? "button" : undefined} className="sr-row"
    data-game-id={game.id} data-results-statistics={RESULTS_STATS_MARKER} tabIndex={openable ? undefined : -1}
    onClick={openable ? onOpen : undefined} aria-haspopup={openable ? "dialog" : undefined}>
    {side("home")}
    <span className="sr-score">
      <span className="sr-pts" data-winner={winner === "home" || undefined}>{game.home.score ?? "—"}</span>
      <span className="sr-dash" aria-hidden="true">–</span>
      <span className="sr-pts" data-winner={winner === "away" || undefined}>{game.away.score ?? "—"}</span>
    </span>
    {side("away")}
    <span className="sr-leaders">{leaders ? <bdi dir="auto">{leaders}</bdi> : !openable && <span title="נתוני המשחק לא זמינים">תוצאה בלבד</span>}</span>
  </Row>;
}
