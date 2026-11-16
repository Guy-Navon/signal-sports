import React, { useEffect, useMemo, useRef, useState } from "react";
import { pageState } from "./resultsPageModel";
import { dateChips, followedTeamIds, playerLines, sideBoxes, streamDays, summaryParts, tileEntries } from "./resultsLayoutModel";
import { formatDayHeading, jerusalemDayKey } from "./resultsFormat";
import ResultRow from "./ResultRow";
import ResultTile from "./ResultTile";
import { PlayersBox, TonightBox } from "./ResultsSide";
import GameDetailDialog from "./GameDetailDialog";
import { RESULTS_STATS_MARKER } from "./resultsStatsBoundary";
import "./results-board.css";

const MESSAGES = { preferences: "עדיין לא בחרת מה מעניין אותך", empty: "אין משחקים להיום", error: "לא הצלחנו לטעון את התוצאות" };
const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export default function ResultsBoard({ games = [], profile = null, hasPreferences = false, loading = false, error = null,
  onRetry = () => {}, getDetail, nowMs = Date.now(), readOnly = false }) {
  const [selected, setSelected] = useState(null), [expanded, setExpanded] = useState(() => new Set());
  const opener = useRef(null), heading = useRef(null), rows = useRef(new Map()), pendingFocus = useRef(null);
  const now = useMemo(() => new Date(nowMs), [nowMs]);
  const state = pageState({ loading, error, hasPreferences, games });
  const followed = useMemo(() => followedTeamIds(profile, games), [profile, games]);
  const model = useMemo(() => ({
    summary: summaryParts(games, now), tiles: tileEntries(games, followed), chips: dateChips(games, now),
    days: streamDays(games, followed, now), tonight: sideBoxes(games, now).tonight, players: playerLines(games, now),
  }), [games, followed, now]);
  useEffect(() => {
    if (pendingFocus.current) rows.current.get(pendingFocus.current)?.focus();
    pendingFocus.current = null;
  }, [expanded]);
  const setRow = id => node => { if (node) rows.current.set(id, node); else rows.current.delete(id); };
  const open = game => event => { opener.current = event.currentTarget; setSelected(game); };
  function close() {
    setSelected(null);
    if (opener.current?.isConnected !== false) opener.current?.focus({ preventScroll: true });
    else heading.current?.focus({ preventScroll: true });
  }
  function reveal(key, hidden) {
    pendingFocus.current = hidden[0]?.id;
    setExpanded(prev => new Set(prev).add(key));
  }
  function jump(dayKey) {
    document.getElementById(`sr-day-${dayKey}`)?.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
  }
  const ready = state === "ready";
  return <div className="sr-board" data-results-statistics={RESULTS_STATS_MARKER}>
    <div className="sg-gutter"><div className="sg-container sr-top">
      <header className="sr-heading"><h1 ref={heading} tabIndex={-1}>תוצאות</h1>
        {ready && model.summary.length > 0 && <p className="sr-summary">{model.summary.map((part, i) => <React.Fragment key={part.label}>
          {i > 0 && " · "}<b>{part.n}</b> {part.label}</React.Fragment>)}</p>}
      </header>
      {state === "loading" && <p className="sr-message" role="status">טוען תוצאות…</p>}
      {!ready && state !== "loading" && <div className="sr-message" role={state === "error" ? "alert" : undefined}><h2>{readOnly && state === "empty" ? "אין תוצאות להצגה כרגע" : MESSAGES[state]}</h2>
        {state === "error" && <button type="button" onClick={onRetry}>נסה שוב</button>}
        {state === "preferences" && !readOnly && <a href="/preferences">בחירת העדפות</a>}
        {state === "empty" && <p>משחקים קרובים ותוצאות חדשות יופיעו כאן כשיהיו זמינים.</p>}
      </div>}
      {ready && model.tiles.length > 0 && <section className="sr-teams" aria-labelledby="sr-teams-title">
        <h2 id="sr-teams-title" className="sr-section-title">הקבוצות שלך</h2>
        <div className="sr-tiles">{model.tiles.map(entry => <ResultTile key={entry.game.id} entry={entry} followed={followed}
          dayLabel={(model.chips.find(c => c.dayKey === (entry.game.localDate || jerusalemDayKey(entry.game.startTime))) || {}).label
            || formatDayHeading(entry.game.localDate, now)} onOpen={open(entry.game)} />)}</div>
      </section>}
    </div></div>
    {ready && <>
      {model.chips.length > 0 && <nav className="sr-datebar" aria-label="קפיצה לתאריך"><div className="sg-gutter"><div className="sg-container">
        <ul>{model.chips.map(chip => <li key={chip.dayKey}><button type="button" onClick={() => jump(chip.dayKey)}><span>{chip.label}</span></button></li>)}</ul>
      </div></div></nav>}
      <div className="sr-band"><div className="sg-gutter"><div className="sg-container sr-cols">
        <div className="sr-panel">
          {model.days.map(day => <section className="sr-day" id={day.dayKey ? `sr-day-${day.dayKey}` : undefined} key={day.dayKey || "undated"}
            aria-label={day.title + (day.sub ? `, ${day.sub}` : "")}>
            <h2 className="sr-day__head"><span>{day.title}</span>{day.sub && <small>{day.sub}</small>}</h2>
            {day.leagues.map(league => {
              const key = `${day.dayKey}|${league.competitionId}`, open_ = expanded.has(key);
              const shown = open_ ? [...league.visible, ...league.hidden] : league.visible;
              return <section key={league.competitionId} className="sr-league" aria-label={league.label}>
                <h3 className="sr-league__head"><bdi dir="auto">{league.label}</bdi></h3>
                {shown.map(game => <ResultRow key={game.id} game={game} followed={followed} rowRef={setRow(game.id)} onOpen={open(game)} />)}
                {!open_ && league.hidden.length > 0 && <button type="button" className="sr-more" aria-expanded="false"
                  onClick={() => reveal(key, league.hidden)}>עוד {league.hidden.length} משחקי <bdi dir="auto">{league.label}</bdi></button>}
              </section>;
            })}
          </section>)}
        </div>
        <aside className="sr-side" aria-label="מידע נוסף">
          <TonightBox tonight={model.tonight} />
          {(!readOnly || model.players.length > 0) && <PlayersBox lines={model.players} readOnly={readOnly} />}
        </aside>
      </div></div></div>
    </>}
    {selected && <GameDetailDialog key={selected.id} game={selected} getDetail={getDetail} onClose={close} />}
  </div>;
}
