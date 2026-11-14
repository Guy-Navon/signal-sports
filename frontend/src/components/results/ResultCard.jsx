import React from "react";
import { resultWinner } from "@/components/feed/signal/resultsStripModel";
import { statusLabel, hasScore } from "./resultsModel";
import { formatGameTime } from "./resultsFormat";
import "@/components/feed/signal/results-strip.css";

// Share the strip's team/score styles and authoritative winner decision. The
// page also includes unfinished games, stage and exact Jerusalem start times.
function TeamRow({ team, winner, showScore }) {
  return (
    <div className={`sg-result__team${winner ? " sg-result__team--winner" : ""}`}>
      <bdi dir="auto">{team.name}</bdi>
      {showScore && <span className="sg-result__score" dir="ltr">{team.score}</span>}
    </div>
  );
}

export default function ResultCard({ game }) {
  const winner = resultWinner(game);
  const time = formatGameTime(game.startTime);
  const showScore = hasScore(game);
  const label = statusLabel(game.status);

  return (
    <article className="sg-results-page__game" data-status={game.status}>
      <div className="sg-results-page__meta">
        <small className="sg-result__meta">
          <bdi dir="auto">{game.competitionHe}</bdi>
          {game.stage && <> · <bdi dir="auto">{game.stage}</bdi></>}
          {time && <> · <time dateTime={game.startTime} dir="ltr">{time}</time></>}
        </small>
        {label && <span className="sg-results-page__status">{label}</span>}
      </div>
      <TeamRow team={game.home} winner={winner === "home"} showScore={showScore} />
      <TeamRow team={game.away} winner={winner === "away"} showScore={showScore} />
    </article>
  );
}
