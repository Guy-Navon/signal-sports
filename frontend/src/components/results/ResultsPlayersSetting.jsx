import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { getMeResultsPlayers, getResultsPlayersCatalog, putMeResultsPlayers } from "@/api/client";
import { searchResultPlayers, toggleResultPlayer } from "./resultsPlayersModel";
import "./results-players.css";

export function ResultsPlayersEditor({ catalog, selected, onChange, onSave, saving = false,
  error = "", saved = false, mode = "preferences" }) {
  const [query, setQuery] = useState("");
  const searchRef = useRef(null);
  const id = useId();
  const matches = searchResultPlayers(catalog, query, selected);
  function toggle(eid) {
    onChange(toggleResultPlayer(selected, eid));
    searchRef.current?.focus({ preventScroll: true });
  }
  return <section className={`sg-form-section sg-results-players sg-results-players--${mode}`}>
    <h2>{mode === "calibration" ? "של מי תרצה לראות שורה בתוצאות?" : "שחקנים בתוצאות"}</h2>
    <p className="sg-form-note">בחירה אישית לחשבון שלך. שורת נתונים במשחקים שלך, בלי לשנות את הפיד.</p>
    <form onSubmit={(event) => { event.preventDefault(); onSave(); }}>
      <fieldset disabled={saving}>
        <label htmlFor={id}>חיפוש שחקן</label>
        <input ref={searchRef} id={id} name="results-player-search" type="search" autoComplete="off"
          value={query} onChange={(event) => setQuery(event.target.value)} placeholder="שם בעברית או באנגלית…" />
        {selected.length > 0 && <ul className="sg-results-players__chips" aria-label="שחקנים שנבחרו">
          {selected.map((eid) => <li key={eid}><bdi dir="auto">{catalog.find(p => p.entity_id === eid)?.name || eid}</bdi>
            <button type="button" aria-label={`הסרת ${catalog.find(p => p.entity_id === eid)?.name || eid}`} onClick={() => toggle(eid)}>×</button>
          </li>)}
        </ul>}
        <ul className="sg-results-players__matches" aria-label="שחקנים לבחירה">
          {matches.map((p) => <li key={p.entity_id}><button type="button" aria-label={`הוספת ${p.name}`} onClick={() => toggle(p.entity_id)}>
            <bdi dir="auto">{p.name}</bdi><span>הוסף +</span>
          </button></li>)}
        </ul>
        {!matches.length && <p className="sg-form-note">לא נמצאו שחקנים נוספים לחיפוש הזה.</p>}
        <button type="submit" className="sg-results-players__save">{saving ? "שומר…" : "שמירת שחקנים"}</button>
      </fieldset>
    </form>
    <p role="status" aria-live="polite" className="sg-form-note">{saved ? "השחקנים נשמרו" : ""}</p>
    {error && <p role="alert" className="sg-results-players__error">{error}</p>}
  </section>;
}

export default function ResultsPlayersSetting({ enabled, onSaved = () => {} }) {
  const [catalog, setCatalog] = useState([]);
  const [selected, setSelected] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const generation = useRef(0);
  const load = useCallback(async () => {
    if (!enabled) return;
    const current = ++generation.current;
    setLoading(true); setLoadError(false);
    try {
      const [choices, available] = await Promise.all([getMeResultsPlayers(), getResultsPlayersCatalog()]);
      if (current !== generation.current) return;
      setCatalog(available.players || []);
      setSelected((choices.players || []).map(p => p.entity_id));
    } catch { if (current === generation.current) setLoadError(true); }
    finally { if (current === generation.current) setLoading(false); }
  }, [enabled]);
  useEffect(() => { load(); return () => { generation.current += 1; }; }, [load]);
  async function save() {
    const current = generation.current;
    setSaving(true); setError(""); setSaved(false);
    try {
      const result = await putMeResultsPlayers(selected);
      if (current !== generation.current) return;
      setSelected(result.players.map(p => p.entity_id)); setSaved(true); onSaved();
    } catch { if (current === generation.current) setError("השמירה נכשלה. אפשר לנסות שוב."); }
    finally { if (current === generation.current) setSaving(false); }
  }
  if (!enabled) return <section className="sg-form-section sg-results-players"><h2>שחקנים בתוצאות</h2>
    <p className="sg-form-note">בחירת שחקנים זמינה בחיבור לחשבון במצב שרת.</p></section>;
  if (loading) return <p role="status" className="sg-form-note">טוען שחקנים לתוצאות…</p>;
  if (loadError) return <section className="sg-form-section sg-results-players"><p role="alert">לא הצלחנו לטעון שחקנים.</p>
    <button type="button" className="sg-results-players__save" onClick={load}>נסה שוב</button></section>;
  return <ResultsPlayersEditor catalog={catalog} selected={selected} onChange={(ids) => { setSelected(ids); setSaved(false); }}
    onSave={save} saving={saving} error={error} saved={saved} />;
}
