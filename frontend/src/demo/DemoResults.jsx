import React, { useMemo, useRef, useState, useEffect } from "react";
import { formatDayHeading, jerusalemDayKey } from "@/components/results/resultsFormat";
import { shortTeamName } from "@/components/results/resultsTeamNames";
import { demoResultsView } from "./demoModel";
import "@/components/results/results-board.css";

// The public demo's results page (#553): direction C with scores only. It is a
// separate composition on purpose: the product's row, tile, board and popup
// import the private statistics renderers, which must stay out of this bundle
// (check-demo-bundle.mjs). Nothing here is interactive except the date bar and
// the long-league "more" button; rows and tiles open nothing.

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const winnerOf = (game) => game.winner ?? (game.home.isWinner ? "home" : game.away.isWinner ? "away" : null);

function FollowDot() {
  return <span className="sr-dot" role="img" aria-label="קבוצה שאתה עוקב אחריה" />;
}

function Row({ game, followed, rowRef }) {
  const winner = winnerOf(game);
  const side = (key) => (
    <span className={`sr-team sr-team--${key}`} data-winner={winner === key || undefined}>
      {followed.has(game[key].id) && key === "home" && <FollowDot />}
      <bdi dir="auto">{shortTeamName(game[key])}</bdi>
      {followed.has(game[key].id) && key === "away" && <FollowDot />}
    </span>
  );
  return (
    <div ref={rowRef} className="sr-row" data-game-id={game.id} tabIndex={-1}>
      {side("home")}
      <span className="sr-score">
        <span className="sr-pts" data-winner={winner === "home" || undefined}>{game.home.score ?? "—"}</span>
        <span className="sr-dash" aria-hidden="true">–</span>
        <span className="sr-pts" data-winner={winner === "away" || undefined}>{game.away.score ?? "—"}</span>
      </span>
      {side("away")}
    </div>
  );
}

function Tile({ entry, followed, dayLabel }) {
  const { game, verdict } = entry;
  const winner = winnerOf(game);
  return (
    <div className="sr-tile" data-game-id={game.id}>
      <span className="sr-tile__meta">
        <span><bdi dir="auto">{game.competitionHe}</bdi> · {dayLabel}</span>
        {verdict && <span className="sr-verdict" data-kind={verdict.kind}>{verdict.label}</span>}
      </span>
      {["home", "away"].map((key) => (
        <span key={key} className="sr-tile__side" data-winner={winner === key || undefined}>
          <span className="sr-tile__team">
            <span className="sr-tile__name">{followed.has(game[key].id) && <FollowDot />}<bdi dir="auto">{shortTeamName(game[key])}</bdi></span>
          </span>
          <span className="sr-tile__pts" dir="ltr">{game[key].score ?? "—"}</span>
        </span>
      ))}
    </div>
  );
}

export default function DemoResults({ games = [], nowMs = Date.now() }) {
  const [expanded, setExpanded] = useState(() => new Set());
  const rows = useRef(new Map());
  const pendingFocus = useRef(null);
  const now = useMemo(() => new Date(nowMs), [nowMs]);
  const view = useMemo(() => demoResultsView(games, now), [games, now]);
  useEffect(() => {
    if (pendingFocus.current) rows.current.get(pendingFocus.current)?.focus();
    pendingFocus.current = null;
  }, [expanded]);

  const jump = (dayKey) => document.getElementById(`sr-day-${dayKey}`)
    ?.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
  const dayLabel = (game) => (view.chips.find((c) => c.dayKey === (game.localDate || jerusalemDayKey(game.startTime))) || {}).label
    || formatDayHeading(game.localDate, now);

  return (
    <div className="sr-board sr-board--demo">
      <div className="sg-gutter"><div className="sg-container sr-top">
        <header className="sr-heading">
          <h1>תוצאות</h1>
          {view.summary.length > 0 && (
            <p className="sr-summary">{view.summary.map((part, i) => (
              <React.Fragment key={part.label}>{i > 0 && " · "}<b>{part.n}</b> {part.label}</React.Fragment>
            ))}</p>
          )}
        </header>
        {view.state === "empty" && (
          <div className="sr-message" role="status">
            <h2>אין תוצאות להצגה כרגע</h2>
            <p>תוצאות חדשות יופיעו כאן בעדכון הבא.</p>
          </div>
        )}
        {view.tiles.length > 0 && (
          <section className="sr-teams" aria-labelledby="sr-teams-title">
            <h2 id="sr-teams-title" className="sr-section-title">הקבוצות שלך</h2>
            <div className="sr-tiles">
              {view.tiles.map((entry) => <Tile key={entry.game.id} entry={entry} followed={view.followed} dayLabel={dayLabel(entry.game)} />)}
            </div>
          </section>
        )}
      </div></div>
      {view.state === "ready" && (
        <>
          {view.chips.length > 0 && (
            <nav className="sr-datebar" aria-label="קפיצה לתאריך"><div className="sg-gutter"><div className="sg-container">
              <ul>{view.chips.map((chip) => (
                <li key={chip.dayKey}><button type="button" onClick={() => jump(chip.dayKey)}><span>{chip.label}</span></button></li>
              ))}</ul>
            </div></div></nav>
          )}
          <div className="sr-band"><div className="sg-gutter"><div className="sg-container sr-cols sr-cols--single">
            <div className="sr-panel">
              {view.days.map((day) => (
                <section className="sr-day" id={day.dayKey ? `sr-day-${day.dayKey}` : undefined} key={day.dayKey || "undated"}
                  aria-label={day.title + (day.sub ? `, ${day.sub}` : "")}>
                  <h2 className="sr-day__head"><span>{day.title}</span>{day.sub && <small>{day.sub}</small>}</h2>
                  {day.leagues.map((league) => {
                    const key = `${day.dayKey}|${league.competitionId}`;
                    const open = expanded.has(key);
                    const shown = open ? [...league.visible, ...league.hidden] : league.visible;
                    return (
                      <section key={league.competitionId} className={`sr-league${day.leagues.length === 1 || league.visible.length + league.hidden.length >= 4 ? " sr-league--wide" : ""}`} aria-label={league.label}>
                        <h3 className="sr-league__head"><bdi dir="auto">{league.label}</bdi></h3>
                        {shown.map((game) => (
                          <Row key={game.id} game={game} followed={view.followed}
                            rowRef={(node) => { if (node) rows.current.set(game.id, node); else rows.current.delete(game.id); }} />
                        ))}
                        {!open && league.hidden.length > 0 && (
                          <button type="button" className="sr-more" aria-expanded="false"
                            onClick={() => { pendingFocus.current = league.hidden[0]?.id; setExpanded((prev) => new Set(prev).add(key)); }}>
                            עוד {league.hidden.length} משחקי <bdi dir="auto">{league.label}</bdi>
                          </button>
                        )}
                      </section>
                    );
                  })}
                </section>
              ))}
            </div>
          </div></div></div>
        </>
      )}
    </div>
  );
}
