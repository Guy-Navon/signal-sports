import React, { useEffect, useRef, useState } from "react";
import { groupResults, pageState, SPORT_LABELS } from "./resultsPageModel";
import { formatDayHeading, jerusalemDayKey } from "./resultsFormat";
import ResultRow from "./ResultRow";
import GameDetailDialog from "./GameDetailDialog";
import { RESULTS_STATS_MARKER } from "./resultsStatsBoundary";
import "./results-board.css";

export default function ResultsBoard({ games = [], hasPreferences = false, loading = false, error = null,
  onRetry = () => {}, getDetail, nowMs = Date.now(), layout = "two-line", popupStyle = "dialog" }) {
  const [selected, setSelected] = useState(null), [count, setCount] = useState(40);
  const opener = useRef(null), heading = useRef(null), rows = useRef(new Map());
  const pendingFocus = useRef(null);
  useEffect(() => {
    if (pendingFocus.current) rows.current.get(pendingFocus.current)?.focus();
    pendingFocus.current = null;
  }, [count]);
  const state = pageState({ loading, error, hasPreferences, games });
  const now = new Date(nowMs), today = jerusalemDayKey(now.toISOString());
  const allGroups = groupResults(games, now);
  const ordered = allGroups.flatMap(d => d.sports.flatMap(s => s.leagues.flatMap(l => l.games)));
  const groups = groupResults(ordered.slice(0, count), now);
  const message = { preferences: "עדיין לא בחרת מה מעניין אותך", empty: "אין משחקים להיום", error: "לא הצלחנו לטעון את התוצאות" };
  function close() {
    setSelected(null);
    if (opener.current?.isConnected !== false) opener.current?.focus({ preventScroll: true });
    else heading.current?.focus({ preventScroll: true });
  }
  return <div className="sg-gutter" data-results-statistics={RESULTS_STATS_MARKER}><div className="sg-container sr-board">
    <header className="sr-heading"><h1 ref={heading} tabIndex={-1}>התוצאות שלך</h1><p>קבוצות, שחקנים וליגות במעקב</p></header>
    {state === "loading" ? <p className="sr-message" role="status">טוען תוצאות…</p>
      : state !== "ready" ? <div className="sr-message" role={state === "error" ? "alert" : undefined}><h2>{message[state]}</h2>
        {state === "error" && <button type="button" onClick={onRetry}>נסה שוב</button>}
        {state === "preferences" && <a href="/preferences">בחירת העדפות</a>}
        {state === "empty" && <p>משחקים קרובים ותוצאות חדשות יופיעו כאן כשיהיו זמינים.</p>}
      </div>
      : <>
        {!groups.some(g => g.dayKey === today) && <p className="sr-today-empty">אין משחקים להיום. הנה המשחקים הקרובים והתוצאות האחרונות.</p>}
        {groups.map(day => <section className="sr-day" key={day.dayKey || "undated"} aria-label={formatDayHeading(day.dayKey, now)}>
          <h2>{formatDayHeading(day.dayKey, now)}</h2>
          {day.sports.map(sport => <section key={sport.sport} className="sr-sport"><h3>{SPORT_LABELS[sport.sport] || sport.sport}</h3>
            {sport.leagues.map(league => <section key={league.competitionId} className="sr-league"><h4><bdi dir="auto">{league.label}</bdi></h4>
              {league.games.map(game => <ResultRow key={game.id} game={game} layout={layout} rowRef={node => { if (node) rows.current.set(game.id, node); else rows.current.delete(game.id); }}
                onOpen={event => { opener.current = event.currentTarget; setSelected(game); }} />)}
            </section>)}
          </section>)}
        </section>)}
        {ordered.length > count && <button type="button" className="sr-more" onClick={() => {
          const next = ordered[count]?.id;
          setCount(n => n + 40);
          // Focus after React commits the newly mounted page, using its owning ref.
          pendingFocus.current = next;
        }}>הצג משחקים נוספים</button>}
      </>}
    {selected && <GameDetailDialog key={selected.id} game={selected} getDetail={getDetail} onClose={close} style={popupStyle} />}
  </div></div>;
}
