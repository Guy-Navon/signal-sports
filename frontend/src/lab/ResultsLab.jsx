import React, { useState } from "react";
import ResultsBoard from "@/components/results/ResultsBoard";
import { normalizeResultsResponse } from "@/components/results/resultsModel";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import { useGround } from "@/components/signal-ui/useGround";
import fixture from "./resultsFixtures.json";
import "./results-lab.css";

const games = normalizeResultsResponse({ has_preferences: true, games: fixture.games }).games;
const getDetail = async id => {
  if (!fixture.details[id]) throw new Error("fixture detail unavailable");
  return fixture.details[id];
};
function chooseParam(name, value) {
  const url = new URL(window.location.href);
  url.searchParams.set(name, value); window.history.replaceState(null, "", url);
}

export default function ResultsLab() {
  const { ground } = useGround();
  const params = new URLSearchParams(window.location.search);
  const [layout, setLayout] = useState(params.get("layout") === "one-line" ? "one-line" : "two-line");
  const [popup, setPopup] = useState(params.get("popup") === "side" ? "side" : "dialog");
  const [state, setState] = useState(params.get("state") || "ready");
  return <main className="signal-ui sr-results-lab" data-ground={ground}>
    <header className="sr-lab-head"><div className="sg-container"><SignalWordmark /><p>מעבדת תוצאות · נתוני המקורות השמורים</p></div></header>
    <div className="sg-gutter"><div className="sg-container sr-lab-controls">
      <div role="group" aria-label="סגנון שורת משחק">{[["two-line", "שתי שורות · ברירת מחדל"], ["one-line", "שורה אחת · חלופה"]].map(([id, label]) =>
        <button key={id} type="button" aria-pressed={layout === id} onClick={() => { setLayout(id); chooseParam("layout", id); }}>{label}</button>)}</div>
      <div role="group" aria-label="סגנון פרטי משחק">{[["dialog", "חלון מרכזי · ברירת מחדל"], ["side", "פאנל צד · חלופה"]].map(([id, label]) =>
        <button key={id} type="button" aria-pressed={popup === id} onClick={() => { setPopup(id); chooseParam("popup", id); }}>{label}</button>)}</div>
      <label>מצב לדוגמה <select value={state} onChange={event => { setState(event.target.value); chooseParam("state", event.target.value); }}>
        <option value="ready">משחקים</option><option value="loading">טעינה</option><option value="error">שגיאה</option>
        <option value="preferences">ללא העדפות</option><option value="empty">אין משחקים</option><option value="unavailable">תוצאות ללא נתונים</option>
      </select></label>
      <p>הבחירה כאן היא להדגמה. בשני סגנונות הפרטים מופיעים כגיליון תחתון בטלפון.</p>
    </div></div>
    <ResultsBoard key={`${state}-${popup}`} games={["empty", "loading"].includes(state) ? [] : state === "unavailable" ? games.map(g => ({ ...g, detailAvailable: false, leaders: [], chosenPlayerLines: [] })) : games}
      hasPreferences={state !== "preferences"} loading={state === "loading"} error={state === "error" ? "fixture failure" : null}
      onRetry={() => setState("ready")} getDetail={getDetail} nowMs={Date.parse(fixture.as_of)} layout={layout} popupStyle={popup} />
  </main>;
}
