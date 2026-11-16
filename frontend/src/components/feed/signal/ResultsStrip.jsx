import React, { Suspense, lazy, useId, useRef, useState } from "react";
import { useMouseDragScroll } from "@/components/shared/useMouseDragScroll";
import { latestFinals, resultStripLabels, resultWinner } from "./resultsStripModel";
import { enterStyle } from "./feedMotionModel";
import "./results-strip.css";

// The box score loads on first open, so the feed bundle stays free of the statistics UI.
const StripGameDetail = lazy(() => import("./StripGameDetail"));

function TeamRow({ team, winner }) {
  return (
    <div className={`sg-result__team${winner ? " sg-result__team--winner" : ""}`}>
      <bdi dir="auto">{team.name}</bdi>
      {/* Keyed by value: a changed score ticks in (#467). */}
      <span key={team.score} className="sg-result__score sg-tick" dir="ltr">{team.score}</span>
    </div>
  );
}

/**
 * A read-only view of results already loaded by AppContext; no router/provider needed.
 * enterBaseMs: when the cells start entering (the feed's load choreography, #467).
 */
export default function ResultsStrip({ results = [], nowMs = Date.now(), enterBaseMs = 0, getDetail = null }) {
  const headingId = useId();
  const [selected, setSelected] = useState(null);
  const opener = useRef(null);
  const games = latestFinals(results, nowMs);
  const { dragging, onPointerDown, onClickCapture } = useMouseDragScroll(games.length > 0);
  if (games.length === 0) return null;

  return (
    <section className="sg-results" aria-labelledby={headingId} style={enterStyle(0, enterBaseMs)}>
      <header className="sg-results__heading">
        <h2 id={headingId}>תוצאות</h2>
        <a className="sg-results__link" href="/results">ללוח המלא</a>
      </header>
      <div
        className={`sg-results__scroller${dragging ? " sg-results__scroller--dragging" : ""}`}
        role="group"
        aria-label="תוצאות משחקים, גלילה אופקית"
        tabIndex={0}
        onPointerDown={onPointerDown}
        onClickCapture={onClickCapture}
      >
        {games.map((game, index) => {
          const labels = resultStripLabels(game, nowMs);
          const winner = resultWinner(game);
          const openable = Boolean(getDetail && game.detailAvailable);
          const Item = openable ? "button" : "article";
          return (
            <Item
              key={game.id}
              className={`sg-result${openable ? " sg-result--open" : ""}`}
              style={enterStyle(index, enterBaseMs)}
              aria-label={[labels.competition, labels.relativeTime, labels.description].filter(Boolean).join(", ")}
              {...(openable ? {
                type: "button",
                "aria-haspopup": "dialog",
                // A drag's ending click is swallowed by the scroller's capture handler.
                onClick: (event) => { opener.current = event.currentTarget; setSelected(game); },
              } : {})}
            >
              <div aria-hidden="true">
                <small className="sg-result__meta">
                  <bdi dir="auto">{labels.competition}</bdi>
                  {labels.relativeTime && <> · <time dateTime={game.startTime}>{labels.relativeTime}</time></>}
                </small>
                <TeamRow team={game.home} winner={winner === "home"} />
                <TeamRow team={game.away} winner={winner === "away"} />
              </div>
            </Item>
          );
        })}
      </div>
      {selected && getDetail && (
        <Suspense fallback={null}>
          <StripGameDetail
            key={selected.id}
            game={selected}
            getDetail={getDetail}
            onClose={() => { setSelected(null); opener.current?.focus?.({ preventScroll: true }); }}
          />
        </Suspense>
      )}
    </section>
  );
}
