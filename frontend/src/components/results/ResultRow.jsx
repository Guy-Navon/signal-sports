import React from "react";
import { chosenLineText } from "./resultsPageModel";
import { formatGameTime } from "./resultsFormat";
import { RESULTS_STATS_MARKER } from "./resultsStatsBoundary";

export default function ResultRow({ game, onOpen, rowRef = null, layout = "two-line" }) {
  const scheduled = game.status === "scheduled";
  const openable = !scheduled && game.detailAvailable;
  const Row = openable ? "button" : "div";
  return <Row ref={rowRef} type={openable ? "button" : undefined} className={`sr-row sr-row--${layout}`}
    data-game-id={game.id} data-results-statistics={RESULTS_STATS_MARKER} tabIndex={openable ? undefined : -1}
    onClick={openable ? onOpen : undefined} aria-haspopup={openable ? "dialog" : undefined}>
    {scheduled && <span className="sr-kickoff">המשחק הבא · <time dateTime={game.startTime}>{formatGameTime(game.startTime) || "שעה תפורסם בהמשך"}</time></span>}
    <span className="sr-sides">
      {["home", "away"].map(side => <span key={side} className="sr-side" data-winner={game.status === "final" && (game.winner ? game.winner === side : game[side].isWinner) || undefined}>
        <span className="sr-team"><bdi dir="auto">{game[side].name}</bdi>{game[side].rank != null && <span className="sr-rank"> [{game[side].rank}]</span>}</span>
        <span className="sr-score" dir="ltr">{scheduled ? "—" : game[side].score ?? "—"}</span>
        {!scheduled && <span className="sr-leaders">{(game.leaders || []).filter(p => p.side === side).map((p, i) => <React.Fragment key={`${p.entity_id || p.name}-${i}`}>
          {i > 0 && " · "}<bdi dir="auto">{p.name || "שחקן לא מזוהה"}</bdi> <span className="sr-num" dir="ltr">{p.value}</span> {p.stat === "goals" ? (p.value === 1 ? "שער" : "שערים") : "נק׳"}
        </React.Fragment>)}</span>}
      </span>)}
    </span>
    {(game.chosenPlayerLines || []).map((p, i) => <span className="sr-chosen-line" key={`${p.entity_id}-${i}`}>
      <bdi dir="auto">{p.name}</bdi><span>{chosenLineText(p, game.sport)}</span>
    </span>)}
    {!scheduled && !game.detailAvailable && <span className="sr-source-note">תוצאה בלבד · נתוני המשחק לא זמינים</span>}
    {openable && <span className="sr-open-hint">פרטי המשחק</span>}
  </Row>;
}
