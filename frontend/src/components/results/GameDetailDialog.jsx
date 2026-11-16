import React, { useEffect, useId, useRef, useState } from "react";
import { RESULTS_STATS_MARKER } from "./resultsStatsBoundary";
import { boxScore, footballEvents, gameLeaders, periodTable, popupHeader, scoreboard, teamComparison, teamFacts } from "./resultsPopupModel";
import { BoxScore, GameLeaders, TeamComparison } from "./GameStats";
import Rank from "./Rank";

const FOCUSABLE = 'button:not([disabled]), a[href], summary, [tabindex="0"]';

function Scoreboard({ game }) {
  const board = scoreboard(game);
  const side = (key) => <div className="sr-board-team" data-winner={board.winner === key || undefined}>
    <span className="sr-board-team__name"><bdi dir="auto">{board[key].name}</bdi><Rank value={game[key].rank} /></span>
    {board[key].top && <span className="sr-board-team__top"><bdi dir="auto">{board[key].top}</bdi></span>}
  </div>;
  return <div className="sr-scoreboard">
    {side("home")}
    <div className="sr-big" aria-label={`${board.home.score} – ${board.away.score}`}>
      <span className="sr-big__score">
        <span data-winner={board.winner === "home" || undefined}>{board.home.score ?? "—"}</span>
        <span className="sr-big__dash" aria-hidden="true">–</span>
        <span data-winner={board.winner === "away" || undefined}>{board.away.score ?? "—"}</span>
      </span>
      <span className="sr-big__status">סיום</span>
    </div>
    {side("away")}
  </div>;
}

function PeriodTable({ table }) {
  return <table className="sr-periods"><caption className="sr-vh">תוצאה לפי רבעים</caption>
    <thead><tr><td />{table.labels.map(label => <th key={label} scope="col">{/^\d+$/.test(label) && <span className="sr-periods__word">רבע </span>}{label}</th>)}<th scope="col">סה״כ</th></tr></thead>
    <tbody>{table.rows.map(row => <tr key={row.side}><th scope="row"><bdi dir="auto">{row.name}</bdi></th>
      {row.values.map((value, i) => <td key={i}>{value}</td>)}<td className="sr-periods__total">{row.total ?? "—"}</td></tr>)}</tbody></table>;
}

function Facts({ facts, game }) {
  return <dl className="sr-facts">{facts.map(fact => <div key={fact.label} className="sr-fact"><dt>{fact.label}</dt>
    <dd><span><span className="sr-vh">{game.home.name} </span>{fact.home}</span><span><span className="sr-vh">{game.away.name} </span>{fact.away}</span></dd></div>)}</dl>;
}

function Tabs({ game, active, onPick, tabRefs, baseId }) {
  const onKeyDown = (event, key) => {
    const next = { ArrowLeft: key === "home" ? "away" : "home", ArrowRight: key === "home" ? "away" : "home", Home: "home", End: "away" }[event.key];
    if (!next) return;
    event.preventDefault(); onPick(next); tabRefs.current[next]?.focus();
  };
  return <div className="sr-tabs" role="tablist" aria-label="קבוצה">
    {["home", "away"].map(key => <button key={key} ref={node => { tabRefs.current[key] = node; }} id={`${baseId}-${key}`} type="button" role="tab"
      aria-selected={active === key} aria-controls={`${baseId}-panel`} tabIndex={active === key ? 0 : -1}
      onClick={() => onPick(key)} onKeyDown={event => onKeyDown(event, key)}><bdi dir="auto">{game[key].name}</bdi></button>)}
  </div>;
}

function FootballEvents({ events, game }) {
  const label = (e) => [e.goals ? (e.goals === 1 ? "שער" : `${e.goals} שערים`) : "", e.yellow ? "כרטיס צהוב" : "", e.red ? "כרטיס אדום" : ""].filter(Boolean).join(" · ");
  if (!events.home.length && !events.away.length) return <p className="sr-note">אין נתוני שערים וכרטיסים למשחק הזה.</p>;
  return <div className="sr-football">{["home", "away"].map(side => <section key={side}>
    <h3><bdi dir="auto">{game[side].name}</bdi></h3>
    {events[side].length ? <ul>{events[side].map((e, i) => <li key={i}><bdi dir="auto">{e.name}</bdi><span>{label(e)}</span></li>)}</ul> : <p className="sr-note">—</p>}
  </section>)}</div>;
}

export default function GameDetailDialog({ game, getDetail, onClose }) {
  const dialogRef = useRef(null), closeRef = useRef(null), tabRefs = useRef({});
  const pointerStartedOutside = useRef(false);
  const titleId = useId(), baseId = useId();
  const [detail, setDetail] = useState(null), [error, setError] = useState(false), [retry, setRetry] = useState(0);
  const [side, setSide] = useState((game.chosenPlayerLines || [])[0]?.side === "away" ? "away" : "home");
  const [view, setView] = useState("players"), [expanded, setExpanded] = useState(false);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
    closeRef.current?.focus({ preventScroll: true });
    const body = typeof document === "undefined" ? null : document.body;
    const overflow = body?.style.overflow;
    if (body) body.style.overflow = "hidden";
    return () => { dialog?.close(); if (body) body.style.overflow = overflow; };
  }, []);
  useEffect(() => {
    let active = true;
    setDetail(null); setError(false);
    Promise.resolve().then(() => getDetail(game.id)).then(result => { if (active) setDetail(result); })
      .catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [game.id, getDetail, retry]);
  const close = () => { dialogRef.current?.close(); onClose(); };
  const outsideDialog = event => {
    if (event.target !== event.currentTarget) return false;
    const rect = event.currentTarget.getBoundingClientRect();
    return event.clientX < rect.left || event.clientX >= rect.right
      || event.clientY < rect.top || event.clientY >= rect.bottom;
  };
  const dismissBackdrop = event => {
    // Both ends must be outside: selecting text or dragging out of the table
    // must not dismiss the dialog. Native backdrop events target the dialog.
    const dismiss = pointerStartedOutside.current && outsideDialog(event);
    pointerStartedOutside.current = false;
    if (dismiss) close();
  };
  // Wrap Tab and Shift+Tab between the close button and the last focusable control.
  const trapFocus = event => {
    if (event.key !== "Tab") return;
    const list = [...(dialogRef.current?.querySelectorAll?.(FOCUSABLE) ?? [])].filter(node => node.tabIndex >= 0);
    const first = closeRef.current, last = list[list.length - 1] || first;
    if (event.shiftKey && event.target === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && event.target === last) { event.preventDefault(); first?.focus(); }
  };
  const basketball = game.sport === "basketball", football = game.sport === "football";
  const table = detail && basketball ? periodTable(detail, game) : null;
  const facts = detail ? teamFacts(detail, game.sport) : [];
  const box = detail && basketball ? boxScore(detail, side, game.sport, expanded) : null;
  const leaders = detail ? gameLeaders(detail, game.sport) : [];
  const comparison = detail ? teamComparison(detail, game) : null;
  return <dialog ref={dialogRef} className="sr-dialog" aria-labelledby={titleId} aria-modal="true"
    data-results-statistics={RESULTS_STATS_MARKER} onKeyDown={trapFocus} onCancel={event => { event.preventDefault(); close(); }}
    onPointerDown={event => { pointerStartedOutside.current = outsideDialog(event); }}
    onPointerCancel={() => { pointerStartedOutside.current = false; }} onClick={dismissBackdrop}>
    <div className="sr-grab" aria-hidden="true" />
    <h2 id={titleId} className="sr-vh"><bdi dir="auto">{game.home.name}</bdi> — <bdi dir="auto">{game.away.name}</bdi></h2>
    <header className="sr-dialog-head"><div><span className="sr-dialog-eyebrow">נתוני המשחק</span>
      <p className="sr-dialog-meta"><bdi dir="auto">{popupHeader(game, detail)}</bdi></p></div>
      <button ref={closeRef} type="button" onClick={close} aria-label="סגירת פרטי המשחק">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
      </button></header>
    <div className="sr-match-summary"><Scoreboard game={game} />{table && <PeriodTable table={table} />}</div>
    {error ? <div className="sr-message" role="alert"><p>לא הצלחנו לטעון את פרטי המשחק.</p>
        <button type="button" onClick={() => { closeRef.current?.focus(); setRetry(n => n + 1); }}>נסה שוב</button></div>
      : !detail ? <p className="sr-message" role="status">טוען את פרטי המשחק…</p>
      : <div className="sr-dialog-body">
        {basketball && <>
          <GameLeaders leaders={leaders} />
          <div className="sr-view-tabs" role="group" aria-label="תצוגת נתוני המשחק">
            <button type="button" aria-pressed={view === "players"} onClick={() => setView("players")}>שחקנים</button>
            <button type="button" aria-pressed={view === "teams"} onClick={() => setView("teams")}>השוואת קבוצות</button>
          </div>
          {view === "teams" ? <TeamComparison comparison={comparison} game={game} /> : <>
            {facts.length > 0 && <Facts facts={facts} game={game} />}
            <Tabs game={game} active={side} onPick={setSide} tabRefs={tabRefs} baseId={baseId} />
            <div id={`${baseId}-panel`} role="tabpanel" aria-labelledby={`${baseId}-${side}`}>
              <BoxScore box={box} labelledBy={`${baseId}-${side}`} expanded={expanded} onExpandedChange={setExpanded} />
            </div>
          </>}
        </>}
        {football && <><TeamComparison comparison={comparison} game={game} />
          <FootballEvents events={footballEvents(detail)} game={game} /></>}
        <p className="sr-source"><span>נתוני המשחק מגיעים מספק תוצאות חיצוני.</span>
          {basketball && <span>2 נק׳ / 3 נק׳ / עונשין: קליעות/ניסיונות</span>}</p>
      </div>}
  </dialog>;
}
