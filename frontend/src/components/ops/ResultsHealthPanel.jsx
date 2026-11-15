import React, { useCallback, useEffect, useRef, useState } from "react";
import { getResultsSyncState } from "@/api/client";
import SectionCard from "@/components/shared/SectionCard";
import { consoleAlert, consoleButton } from "./consoleStyles";

const STATUS = { ok: "תקין", partial: "חלקי", error: "שגיאה", rate_limited: "מוגבל בקצב" };
const REASON = { default: "ספק ברירת מחדל", routed: "מקור מוגדר", disabled: "המקור כבוי",
  never_succeeded: "טרם הצליח", stale: "המקור מיושן", stale_no_fallback: "מיושן, ללא גיבוי עדכני" };

function dateTime(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? new Intl.DateTimeFormat("he-IL", {
    timeZone: "Asia/Jerusalem", dateStyle: "short", timeStyle: "short",
  }).format(date) : "—";
}

function Field({ label, children }) {
  return <div className="min-w-0"><dt className="text-text-dim">{label}</dt>
    <dd className="text-text-secondary break-words"><bdi dir="auto">{children ?? "—"}</bdi></dd></div>;
}

export function ResultsHealthView({ health }) {
  if (!health || health.error) return <p role="alert" className={consoleAlert("error")}>לא ניתן לקרוא את בריאות המקורות כרגע.</p>;
  const providers = Array.isArray(health.providers) ? health.providers : [];
  const competitions = Array.isArray(health.competitions) ? health.competitions : [];
  return <div className="space-y-4 text-xs">
    {health.config_error && <p role="alert" className={consoleAlert("error")}>שגיאה בהגדרות מקורות התוצאות.</p>}
    <div className="space-y-3">
      <h3 className="font-semibold text-text-secondary">ספקי תוצאות</h3>
      {!providers.length && <p className="text-text-dim">טרם נרשמו נתוני ספקים.</p>}
      {providers.map((p) => <section key={p.provider} className="border border-border rounded-lg p-3 space-y-2">
        <h4 className="font-semibold"><bdi dir="auto">{p.provider}</bdi></h4>
        <dl className="grid grid-cols-2 gap-3">
          <Field label="מצב">{p.enabled === false ? "כבוי" : STATUS[p.last_status] || "טרם רץ"}</Field>
          <Field label="הצלחה אחרונה">{dateTime(p.last_success_at)}</Field>
          <Field label="שגיאה אחרונה">{p.last_error || "—"}</Field>
          <Field label="כשלים רצופים">{p.consecutive_failures ?? 0}</Field>
          <Field label="כשלים במבנה נתונים">{p.shape_failures ?? 0}</Field>
          <Field label="חסימה עד">{dateTime(p.rate_limited_until)}</Field>
        </dl>
      </section>)}
    </div>
    <div className="space-y-3">
      <h3 className="font-semibold text-text-secondary">המקור שמוצג בכל תחרות</h3>
      {!competitions.length && <p className="text-text-dim">אין עדיין נתוני תחרויות.</p>}
      {competitions.map((c) => <section key={c.competition_id} className="border border-border rounded-lg p-3 space-y-2">
        <h4 className="font-semibold"><bdi dir="auto">{c.competition_id}</bdi></h4>
        <dl className="grid grid-cols-2 gap-3">
          <Field label="מקור מוצג">{c.serving}</Field>
          <Field label="סיבה">{REASON[c.reason] || c.reason || "—"}</Field>
          {Object.entries(c.freshness || {}).map(([provider, value]) => <Field key={provider} label={`עדכניות ${provider}`}>
            {value?.age_hours == null ? "טרם הצליח" : `${new Intl.NumberFormat("he-IL", { maximumFractionDigits: 1 }).format(value.age_hours)} שעות`}
            {value?.last_status ? ` · ${STATUS[value.last_status] || value.last_status}` : ""}
          </Field>)}
        </dl>
      </section>)}
    </div>
  </div>;
}

export default function ResultsHealthPanel({ isBackendMode, isAdmin }) {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const generation = useRef(0);
  const load = useCallback(async () => {
    if (!isBackendMode || !isAdmin) return;
    const current = ++generation.current;
    setLoading(true); setError(false);
    try {
      const state = await getResultsSyncState();
      if (!state.health || state.health.error) throw new Error("health unavailable");
      if (current === generation.current) setHealth(state.health);
    } catch {
      if (current === generation.current) setError(true);
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [isBackendMode, isAdmin]);
  useEffect(() => { load(); return () => { generation.current += 1; }; }, [load]);
  return <SectionCard title="בריאות מקורות התוצאות">
    {!isBackendMode || !isAdmin ? <p className="text-xs text-text-dim">נתוני המקורות זמינים למנהל במצב שרת.</p>
      : loading ? <p role="status" className="text-xs text-text-dim">טוען את מצב המקורות…</p>
      : error ? <div className="space-y-2"><p role="alert" className={consoleAlert("error")}>לא הצלחנו לטעון את מצב המקורות.</p>
        <button type="button" onClick={load} className={consoleButton("ghost", "min-h-11")}>נסה שוב</button></div>
      : <ResultsHealthView health={health} />}
  </SectionCard>;
}
