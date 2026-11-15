import React from "react";
import { shortTeamName } from "./resultsTeamNames";

// The side column (desktop) and, for the tonight box, the phone's box above the
// stream. A box with nothing real to say is not drawn.
export function TonightBox({ tonight }) {
  if (!tonight) return null;
  return <section className="sr-box sr-box--tonight" aria-labelledby="sr-tonight-title">
    <h3 id="sr-tonight-title">{tonight.title}</h3>
    <ul>{tonight.items.map(({ game, time, day }) => <li key={game.id} className="sr-box__item">
      <span className="sr-box__main"><bdi dir="auto">{shortTeamName(game.home)} – {shortTeamName(game.away)}</bdi>
        <span className="sr-box__meta"><bdi dir="auto">{game.competitionHe}</bdi>{tonight.title === "הקרוב" && <> · {day}</>}</span></span>
      <time className="sr-box__time" dateTime={game.startTime} dir="ltr">{time || "—"}</time>
    </li>)}</ul>
  </section>;
}

export function PlayersBox({ lines }) {
  return <section className="sr-box sr-box--players" aria-labelledby="sr-players-title">
    <h3 id="sr-players-title">השחקנים שלך</h3>
    {lines.length > 0 && <ul>{lines.map(line => <li key={line.key} className="sr-box__item sr-box__item--stack">
      <span className="sr-box__main"><span><bdi dir="auto">{line.name}</bdi>{line.stats && <> · <span className="sr-num">{line.stats}</span></>}</span>
        <span className="sr-box__meta">{line.day}{line.score && <> · <bdi dir="auto">{line.score}</bdi></>}{line.minutes && <> · {line.minutes}</>}</span></span>
    </li>)}</ul>}
    <a className="sr-box__link" href="/preferences">בחירת שחקנים לתוצאות ›</a>
  </section>;
}
