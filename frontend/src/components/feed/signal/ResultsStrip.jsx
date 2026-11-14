import React, { useEffect, useId, useRef, useState } from "react";
import { latestFinals, resultStripLabels, resultWinner } from "./resultsStripModel";
import { enterStyle } from "./feedMotionModel";
import "./results-strip.css";

function useMouseDragScroll(active) {
  const cleanup = useRef(null);
  const suppressClick = useRef(false);
  const [dragging, setDragging] = useState(false);

  useEffect(() => () => cleanup.current?.(), [active]);

  function onPointerDown(event) {
    suppressClick.current = false;
    if (event.pointerType !== "mouse" || event.button !== 0) return;
    cleanup.current?.();
    const scroller = event.currentTarget;
    const doc = scroller.ownerDocument;
    const { pointerId, clientX: startX } = event;
    const startScroll = scroller.scrollLeft;
    let started = false;

    function finish() {
      doc.removeEventListener("pointermove", move);
      doc.removeEventListener("pointerup", end);
      doc.removeEventListener("pointercancel", end);
      scroller.removeEventListener("lostpointercapture", end);
      cleanup.current = null;
      setDragging(false);
      if (scroller.hasPointerCapture(pointerId)) scroller.releasePointerCapture(pointerId);
    }

    function move(pointer) {
      if (pointer.pointerId !== pointerId) return;
      if (!(pointer.buttons & 1)) {
        finish();
        return;
      }
      const delta = pointer.clientX - startX;
      if (!started) {
        if (Math.abs(delta) <= 5) return;
        started = true;
        suppressClick.current = true;
        scroller.setPointerCapture(pointerId);
        setDragging(true);
        doc.getSelection()?.removeAllRanges();
      }
      pointer.preventDefault();
      // RTL scrollLeft is zero or negative; content follows the hand in either direction.
      scroller.scrollLeft = startScroll - delta;
    }

    function end(pointer) {
      if (pointer.pointerId === pointerId) finish();
    }

    // Track this mouse only, including a release outside the strip before capture.
    doc.addEventListener("pointermove", move, { passive: false });
    doc.addEventListener("pointerup", end);
    doc.addEventListener("pointercancel", end);
    scroller.addEventListener("lostpointercapture", end);
    cleanup.current = finish;
  }

  function onClickCapture(event) {
    if (!suppressClick.current) return;
    suppressClick.current = false;
    // Keyboard activation has no pointer click count, even after a cancelled drag.
    if (event.detail === 0) return;
    event.preventDefault();
    event.stopPropagation();
  }

  return { dragging, onPointerDown, onClickCapture };
}

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
export default function ResultsStrip({ results = [], nowMs = Date.now(), enterBaseMs = 0 }) {
  const headingId = useId();
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
          return (
            <article
              key={game.id}
              className="sg-result"
              style={enterStyle(index, enterBaseMs)}
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
