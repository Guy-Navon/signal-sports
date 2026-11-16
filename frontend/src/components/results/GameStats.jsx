import React, { useLayoutEffect, useRef } from "react";

const COLUMNS = {
  min: ["דק׳", "דקות"], pts: ["נק׳", "נקודות"], reb: ["ריב׳", "ריבאונדים"], ast: ["אס׳", "אסיסטים"],
  stl: ["חט׳", "חטיפות"], blk: ["חס׳", "חסימות"], tov: ["איב׳", "איבודים"], pf: ["עב׳", "עבירות"],
  oreb: ["ריב׳ התק׳", "ריבאונד התקפה"], dreb: ["ריב׳ הג׳", "ריבאונד הגנה"],
  fg: ["מהשדה", "קליעות מהשדה / ניסיונות"], fgpct: ["אחוז שדה", "אחוז קליעה מהשדה"],
  fg2: ["2 נק׳", "קליעות לשתיים / ניסיונות"], fg3: ["3 נק׳", "קליעות לשלוש / ניסיונות"],
  fg3pct: ["אחוז לשלוש", "אחוז קליעה לשלוש"], ft: ["עונשין", "קליעות עונשין / ניסיונות"],
  ftpct: ["אחוז עונשין", "אחוז קליעה מהעונשין"], pm: ["+/-", "פלוס / מינוס"], rating: ["מדד", "מדד שחקן מהמקור"],
};
const number = value => new Intl.NumberFormat("he-IL", { maximumFractionDigits: 2 }).format(value);
const cell = (row, col) => row[col] == null ? "—" : col === "pm" && row[col] > 0 ? `+${row[col]}` : row[col];

export function GameLeaders({ leaders }) {
  if (!leaders.length) return null;
  return <section className="sr-game-leaders" aria-label="מצטייני המשחק">
    {leaders.map(leader => <div key={leader.key} className="sr-game-leader">
      <span className="sr-game-leader__label">{leader.label}</span>
      <strong className="sr-game-leader__value">{leader.value}</strong>
      <bdi className="sr-game-leader__name" dir="auto" title={leader.names}>{leader.names}</bdi>
    </div>)}
  </section>;
}

export function BoxScore({ box, labelledBy, expanded, onExpandedChange }) {
  const scrollRef = useRef(null);
  // Switching density changes the table width. In RTL, iOS Safari keeps a stale offset and
  // lands at the far end (players clipped on the left) until the next touch, so start over.
  useLayoutEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) return undefined;
    scroller.scrollLeft = 0;
    if (typeof requestAnimationFrame !== "function") return undefined;
    const frame = requestAnimationFrame(() => { scroller.scrollLeft = 0; });
    return () => cancelAnimationFrame(frame);
  }, [expanded]);
  if (!box.groups.length) return <p className="sr-note">אין נתוני שחקנים למשחק הזה.</p>;
  return <>
    <div className="sr-box-toolbar">
      <h3>סטטיסטיקת שחקנים</h3>
      <div className="sr-density" role="group" aria-label="פירוט סטטיסטיקה">
        <button type="button" aria-pressed={!expanded} onClick={() => onExpandedChange(false)}>בסיסי</button>
        <button type="button" aria-pressed={expanded} onClick={() => onExpandedChange(true)}>מורחב</button>
      </div>
    </div>
    <p className="sr-box-hint">קליעות/ניסיונות · גללו אופקית לעוד נתונים</p>
    <div className="sr-box-scroll" tabIndex={0} ref={scrollRef}>
      <table className="sr-box-table" aria-labelledby={labelledBy}>
        <thead><tr><th scope="col" className="sr-p">שחקן</th>{box.columns.map(col => <th key={col} scope="col" title={COLUMNS[col][1]} aria-label={COLUMNS[col][1]}>{COLUMNS[col][0]}</th>)}</tr></thead>
        {box.groups.map(group => <tbody key={group.key}>
          {group.label && <tr className="sr-box-grp"><th scope="rowgroup" colSpan={box.columns.length + 1}>{group.label}</th></tr>}
          {group.rows.map(row => <tr key={row.key} data-top={row.top || undefined}>
            <th scope="row" className="sr-p"><span className="sr-player-name"><bdi dir="auto" title={row.name}>{row.name}</bdi>
              {row.top && <span className="sr-player-star" title="הקלע המוביל בקבוצה" aria-label="הקלע המוביל בקבוצה">★</span>}</span></th>
            {box.columns.map(col => <td key={col} dir="ltr" className={col === "pts" ? "sr-pts-col" : undefined}>{cell(row, col)}</td>)}
          </tr>)}
        </tbody>)}
        {box.totals && <tfoot><tr><th scope="row" className="sr-p">סך שחקנים</th>
          {box.columns.map(col => <td key={col} dir="ltr">{cell(box.totals, col)}</td>)}
        </tr></tfoot>}
      </table>
    </div>
  </>;
}

export function TeamComparison({ comparison, game }) {
  if (!comparison.rows.length && !comparison.shooting.length) return <p className="sr-note">אין נתוני השוואה למשחק הזה.</p>;
  const percent = value => value == null ? "—" : `${value}%`;
  return <section className="sr-comparison" aria-label="השוואת נתוני הקבוצות">
    <div className="sr-comparison-legend">{["home", "away"].map(side => <span key={side} data-side={side}>
      <i aria-hidden="true" /><bdi dir="auto">{game[side].name}</bdi></span>)}</div>
    {comparison.shooting.length > 0 && <div className="sr-shooting">{comparison.shooting.map(shot => <div key={shot.key} className="sr-shoot-card">
      <h3>{shot.label}</h3><div className="sr-shoot-values">{["home", "away"].map(side => <div key={side} data-side={side}>
        <span className="sr-vh">{game[side].name}</span>
        <strong dir="ltr">{percent(shot[side].percent)}</strong><span dir="ltr">{shot[side].line}</span>
      </div>)}</div>
      <div className="sr-shoot-meters" aria-hidden="true">{["home", "away"].map(side => <span key={side} data-side={side}>
        <i style={{ inlineSize: `${shot[side].percent ?? 0}%` }} /></span>)}</div>
    </div>)}</div>}
    <div className="sr-compare-list">{comparison.rows.map(row => <div key={row.key} className="sr-compare-row">
      <div className="sr-compare-values"><b data-best={row.home !== row.away && (row.lowerBetter ? row.home < row.away : row.home > row.away) || undefined}>
        <span className="sr-vh">{game.home.name} </span>{number(row.home)}</b>
        <span>{row.label}</span><b data-best={row.home !== row.away && (row.lowerBetter ? row.away < row.home : row.away > row.home) || undefined}>
          <span className="sr-vh">{game.away.name} </span>{number(row.away)}</b></div>
      <div className="sr-compare-bars" aria-hidden="true"><span data-side="home" style={{ inlineSize: `${row.homeShare}%` }} />
        <span data-side="away" style={{ inlineSize: `${100 - row.homeShare}%` }} /></div>
    </div>)}</div>
  </section>;
}
