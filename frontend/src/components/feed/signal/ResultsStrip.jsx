import React, { useId } from "react";
import { latestFinals, resultStripLabels, resultWinner } from "./resultsStripModel";
import "./results-strip.css";

function TeamRow({ team, winner }) {
  return (
    <div className={`sg-result__team${winner ? " sg-result__team--winner" : ""}`}>
      <bdi dir="auto">{team.name}</bdi>
      <span className="sg-result__score" dir="ltr">{team.score}</span>
    </div>
  );
}

/** A read-only view of results already loaded by AppContext; no router/provider needed. */
export default function ResultsStrip({ results = [], nowMs = Date.now() }) {
  const headingId = useId();
  const games = latestFinals(results, nowMs);
  if (games.length === 0) return null;

  return (
    <section className="sg-results" aria-labelledby={headingId}>
      <header className="sg-results__heading">
        <h2 id={headingId}>תוצאות</h2>
        <a className="sg-results__link" href="/results">ללוח המלא</a>
      </header>
      <div
        className="sg-results__scroller"
        role="group"
        aria-label="תוצאות משחקים, גלילה אופקית"
        tabIndex={0}
      >
        {games.map((game) => {
          const labels = resultStripLabels(game, nowMs);
          const winner = resultWinner(game);
          return (
            <article
              key={game.id}
              className="sg-result"
              aria-label={[labels.competition, labels.relativeTime, labels.description].filter(Boolean).join(", ")}
            >
              <div aria-hidden="true">
                <small className="sg-result__meta">
                  <bdi dir="auto">{labels.competition}</bdi>
                  {labels.relativeTime && <> · <time dateTime={game.startTime}>{labels.relativeTime}</time></>}
                </small>
                <TeamRow team={game.home} winner={winner === "home"} />
                <TeamRow team={game.away} winner={winner === "away"} />
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
