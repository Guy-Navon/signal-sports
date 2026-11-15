import React from "react";
import { FollowDot } from "./ResultRow";
import { chosenLineText } from "./resultsPageModel";
import { leadersText } from "./resultsLayoutModel";
import { shortTeamName } from "./resultsTeamNames";
import { RESULTS_STATS_MARKER } from "./resultsStatsBoundary";

// A "your teams" tile: the whole tile opens the game popup.
export default function ResultTile({ entry, followed, dayLabel, onOpen, tileRef = null }) {
  const { game, verdict, chosen } = entry;
  const openable = game.detailAvailable;
  const Tile = openable ? "button" : "div";
  const winner = game.winner ?? (game.home.isWinner ? "home" : game.away.isWinner ? "away" : null);
  const leaders = leadersText(game);
  return <Tile ref={tileRef} type={openable ? "button" : undefined} className="sr-tile" data-game-id={game.id}
    data-results-statistics={RESULTS_STATS_MARKER} tabIndex={openable ? undefined : -1}
    onClick={openable ? onOpen : undefined} aria-haspopup={openable ? "dialog" : undefined}>
    <span className="sr-tile__meta"><span><bdi dir="auto">{game.competitionHe}</bdi> · {dayLabel}</span>
      {verdict && <span className="sr-verdict" data-kind={verdict.kind}>{verdict.label}</span>}</span>
    {["home", "away"].map(key => <span key={key} className="sr-tile__side" data-winner={winner === key || undefined}>
      <span className="sr-tile__name">{followed.has(game[key].id) && <FollowDot />}<bdi dir="auto">{shortTeamName(game[key])}</bdi>
        {game[key].rank != null && <span className="sr-rank" dir="ltr">[{game[key].rank}]</span>}</span>
      <span className="sr-tile__pts" dir="ltr">{game[key].score ?? "—"}</span>
    </span>)}
    {chosen && chosenLineText({ stats: chosen.stats }, game.sport) &&
      <span className="sr-chosen"><b><bdi dir="auto">{chosen.name}</bdi></b> {chosenLineText({ stats: chosen.stats }, game.sport)}</span>}
    {leaders && <span className="sr-tile__leaders"><bdi dir="auto">{leaders}</bdi></span>}
  </Tile>;
}
