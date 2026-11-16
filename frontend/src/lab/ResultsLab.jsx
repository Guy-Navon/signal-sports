import React, { useState } from "react";
import ResultsBoard from "@/components/results/ResultsBoard";
import { normalizeResultsResponse } from "@/components/results/resultsModel";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import { useGround } from "@/components/signal-ui/useGround";
import fixture from "./resultsFixtures.json";
import "./results-lab.css";

// Lab-only profile: follows both Maccabi clubs and Portland, including old team cards.
const profile = { profileV2: { scope_affinities: ["team:maccabi_tlv_bb", "team:maccabi_tlv_fc", "team:portland_blazers"]
  .map(target_id => ({ scope: "team", target_id, level: 2, source: "explicit" })) } };

// Synthetic filler (documented in RESULTS_FIXTURES.md): extra NBA finals so a league
// with more than five games on one day shows its collapse. Never from a provider.
const FILLER = [["team:new_orleans_pelicans", "ניו אורלינס פליקנס", 108, "team:denver_nuggets", "דנבר נאגטס", 116, "Jokic 26 · Williamson 24"],
  ["team:cleveland_cavaliers", "קליבלנד קאבלירס", 127, "team:dallas_mavericks", "דאלאס מאבריקס", 117, "Irving 34 · Proctor 24"],
  ["team:miami_heat", "מיאמי היט", 137, "team:detroit_pistons", "דטרויט פיסטונס", 117, "Antetokounmpo 34 · Cunningham 33"],
  ["team:memphis_grizzlies", "ממפיס גריזליס", 129, "team:brooklyn_nets", "ברוקלין נטס", 110, "Coward 23 · Randle 22"],
  ["team:minnesota_timberwolves", "מינסוטה טימברוולבס", 106, "team:chicago_bulls", "שיקגו בולס", 117, "Powell 24 · Dosunmu 24"],
  ["team:la_clippers", "לוס אנג'לס קליפרס", 113, "team:okc_thunder", "אוקלהומה סיטי ת'אנדר", 112, "Gilgeous-Alexander 40 · Lopez 26"]];
const fillerGames = FILLER.map(([hid, hname, hs, aid, aname, as, leaders], i) => ({
  id: `lab_filler_${i}`, competition_id: "comp:nba", competition_he: "NBA", competition_en: "NBA", sport: "basketball", season: "2026-2027", stage: null,
  status: "final", start_time: `2026-11-14T0${i}:00:00+00:00`, local_date: "2026-11-14", winner: hs > as ? "home" : "away", relevance_reason: "",
  home: { id: hid, name: hname, name_provider: hname, score: hs, is_winner: hs > as, rank: null },
  away: { id: aid, name: aname, name_provider: aname, score: as, is_winner: as > hs, rank: null },
  leaders: String(leaders).split(" · ").map((text, n) => ({ side: n ? "away" : "home", name: text.replace(/ \d+$/, ""), entity_id: null, stat: "points", value: Number(text.match(/\d+$/)[0]) })),
  chosen_player_lines: [], venue: null, attendance: null, detail_available: false,
}));
const getDetail = async id => {
  if (!fixture.details[id]) throw new Error("fixture detail unavailable");
  return fixture.details[id];
};
function chooseParam(name, value) {
  const url = new URL(window.location.href);
  if (value) url.searchParams.set(name, value); else url.searchParams.delete(name);
  window.history.replaceState(null, "", url);
}

export default function ResultsLab() {
  const { ground } = useGround();
  const params = new URLSearchParams(window.location.search);
  const embed = params.get("embed") === "1";
  const [state, setState] = useState(params.get("state") || "ready");
  const [fillers, setFillers] = useState(params.get("fillers") === "1");
  const [phone, setPhone] = useState(false);
  const source = fillers ? [...fixture.games, ...fillerGames] : fixture.games;
  const games = normalizeResultsResponse({ has_preferences: true, games: source }).games;
  const shown = ["empty", "loading"].includes(state) ? [] : state === "unavailable"
    ? games.map(g => ({ ...g, detailAvailable: false, leaders: [], chosenPlayerLines: [] })) : games;
  const board = <ResultsBoard key={`${state}-${fillers}`} games={shown} profile={profile}
    hasPreferences={state !== "preferences"} loading={state === "loading"} error={state === "error" ? "fixture failure" : null}
    onRetry={() => setState("ready")} getDetail={getDetail} nowMs={Date.parse(fixture.as_of)} />;
  if (embed) return <main className="signal-ui sr-results-lab" data-ground={ground}>{board}</main>;
  const frame = new URL(window.location.href);
  frame.searchParams.set("embed", "1");
  return <main className="signal-ui sr-results-lab" data-ground={ground}>
    <header className="sr-lab-head"><div className="sg-container"><SignalWordmark /><p>מעבדת תוצאות · כיוון ג׳ · נתוני המקורות השמורים</p></div></header>
    <div className="sg-gutter"><div className="sg-container sr-lab-controls">
      <label>מצב לדוגמה <select value={state} onChange={event => { setState(event.target.value); chooseParam("state", event.target.value); }}>
        <option value="ready">משחקים</option><option value="loading">טעינה</option><option value="error">שגיאה</option>
        <option value="preferences">ללא העדפות</option><option value="empty">אין משחקים</option><option value="unavailable">תוצאות ללא נתונים</option>
      </select></label>
      <div role="group" aria-label="משחקי NBA לדוגמה">
        <button type="button" aria-pressed={fillers} onClick={() => { setFillers(!fillers); chooseParam("fillers", fillers ? "" : "1"); }}>משחקי NBA סינתטיים להדגמת הקיפול</button></div>
      <div role="group" aria-label="רוחב">
        <button type="button" aria-pressed={phone} onClick={() => setPhone(!phone)}>תצוגת טלפון (390)</button></div>
      <p>המשחקים האמיתיים הם מהנתונים השמורים. משחקי ה-NBA הסינתטיים נוספים רק להדגמה ואין להם פרטי משחק.</p>
    </div></div>
    {phone ? <div className="sr-lab-phone"><iframe title="תצוגת טלפון" src={frame.toString()} width="390" height="844" /></div> : board}
  </main>;
}
