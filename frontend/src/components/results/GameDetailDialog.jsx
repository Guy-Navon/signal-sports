import React, { useEffect, useId, useRef, useState } from "react";
import { RESULTS_STATS_MARKER } from "./resultsStatsBoundary";
import { statLabel, teamStatEntries } from "./resultsPageModel";

const shown = value => value == null ? "—" : value;
export default function GameDetailDialog({ game, getDetail, onClose, style = "dialog" }) {
  const dialogRef = useRef(null), closeRef = useRef(null);
  const titleId = useId();
  const [detail, setDetail] = useState(null), [error, setError] = useState(false), [retry, setRetry] = useState(0);
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
  const basketball = game.sport === "basketball";
  const keys = basketball ? ["points", "rebounds", "assists"] : ["goals", "assists", "yellow_cards", "red_cards"];
  return <dialog ref={dialogRef} className={`sr-dialog sr-dialog--${style}`} aria-labelledby={titleId} aria-modal="true"
    data-results-statistics={RESULTS_STATS_MARKER} onCancel={event => { event.preventDefault(); onClose(); }}>
    <header className="sr-dialog-head"><h2 id={titleId}><bdi dir="auto">{game.home.name}</bdi> — <bdi dir="auto">{game.away.name}</bdi></h2>
      <button ref={closeRef} type="button" onClick={onClose} aria-label="סגירת פרטי המשחק">×</button></header>
    {error ? <div className="sr-message" role="alert"><p>לא הצלחנו לטעון את פרטי המשחק.</p><button type="button" onClick={() => setRetry(n => n + 1)}>נסה שוב</button></div>
      : !detail ? <p className="sr-message" role="status">טוען את פרטי המשחק…</p>
      : <div className="sr-dialog-body">
        <p className="sr-venue">{detail.venue && <bdi dir="auto">{detail.venue}</bdi>}{detail.attendance != null && <span> · {new Intl.NumberFormat("he-IL").format(detail.attendance)} צופים</span>}</p>
        {["home", "away"].map(side => <section key={side} className="sr-box-side"><h3><bdi dir="auto">{game[side].name}</bdi></h3>
          <div className="sr-table-scroll" tabIndex={0} role="region" aria-label={`נתוני שחקנים ${game[side].name}`}>
            <table><thead><tr><th scope="col">שחקן</th>{keys.map(key => <th key={key} scope="col">{statLabel(key)}</th>)}<th scope="col">דקות</th></tr></thead>
              <tbody>{(detail.players || []).filter(p => p.side === side).map((p, i) => <tr key={`${p.source_player_id || p.entity_id || i}`}>
                <th scope="row"><bdi dir="auto">{p.name || "שחקן לא מזוהה"}</bdi></th>{keys.map(key => <td dir="ltr" key={key}>{shown(p.stats?.[key] ?? p.stats?.[{ rebounds: "TotalRebounds", assists: "Assistances", points: "Points" }[key]])}</td>)}
                <td dir="ltr">{p.minutes == null ? "—" : new Intl.NumberFormat("he-IL", { maximumFractionDigits: 1 }).format(p.minutes)}</td>
              </tr>)}</tbody></table>
          </div>
          <details className="sr-extra"><summary>כל נתוני השחקנים</summary>
            {(detail.players || []).filter(p => p.side === side).map((p, i) => <div key={i} className="sr-native-player"><h4><bdi dir="auto">{p.name || "שחקן לא מזוהה"}</bdi></h4>
              <dl>{Object.entries(p.stats || {}).filter(([, v]) => typeof v !== "boolean" && v != null).map(([key, value]) => <div key={key}><dt><bdi dir="auto">{statLabel(key)}</bdi></dt><dd><bdi dir="auto">{String(value)}</bdi></dd></div>)}</dl>
            </div>)}
          </details>
          <h4>נתוני קבוצה</h4><dl className="sr-team-stats">{teamStatEntries(detail.team_stats?.[side]).map(([label, value]) => <div key={label}><dt><bdi dir="auto">{label}</bdi></dt><dd><bdi dir="auto">{String(value)}</bdi></dd></div>)}</dl>
        </section>)}
      </div>}
  </dialog>;
}
