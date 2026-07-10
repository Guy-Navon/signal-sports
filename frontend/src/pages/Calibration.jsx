import React, { useEffect, useMemo, useState } from "react";
import { useApp } from "@/context/AppContext";
import { SlidersHorizontal, RefreshCw, AlertCircle, CheckCircle2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getCalibrationItems,
  previewCalibration,
  applyCalibration,
  getCalibrationResponses,
  applyMeCalibration,
  getMeCalibrationResponses,
} from "@/api/client";
import PageHeader from "@/components/shared/PageHeader";
import SectionCard from "@/components/shared/SectionCard";
import StatCard from "@/components/shared/StatCard";
import { consoleButton, consoleAlert } from "@/components/ops/consoleStyles";

/**
 * Calibration V2 (issue #33) — backend-owned flow: the versioned dataset,
 * the hierarchical inference and the persistent apply all live in the
 * backend. This page only collects ratings and renders the results; there
 * is no frontend inference and no frontend-only sandbox state anymore.
 */

const RATING_BUTTONS = [
  { key: "push", label: "תעדכן אותי מיד", tone: "text-signal-push border-signal-push/40 bg-signal-push/10" },
  { key: "interesting", label: "מעניין", tone: "text-signal-high border-signal-high/40 bg-signal-high/10" },
  { key: "neutral", label: "סבבה, לא קריטי", tone: "text-signal-feed border-signal-feed/40 bg-signal-feed/10" },
  { key: "not_interesting", label: "לא מעניין", tone: "text-text-secondary border-border bg-surface-2" },
  { key: "never_show", label: "אל תראה לי כאלה", tone: "text-signal-hidden border-signal-hidden/40 bg-signal-hidden/10" },
];

const SPORT_LABELS = { basketball: "כדורסל", football: "כדורגל", tennis: "טניס" };
const LEVEL_LABELS = {
  "-2": "לא לראות בכלל", "-1": "עניין נמוך", 0: "עניין בינוני",
  1: "עניין גבוה", 2: "עניין מאוד גבוה",
};

function ItemCard({ item, rating, onRate }) {
  return (
    <div className="bg-surface-1 border border-border rounded-[10px] p-3">
      <div className="text-sm text-foreground mb-1">{item.title}</div>
      <div className="text-xs text-text-dim mb-2">{SPORT_LABELS[item.sport] ?? item.sport}</div>
      <div className="flex gap-1.5 flex-wrap">
        {RATING_BUTTONS.map(({ key, label, tone }) => (
          <button
            key={key}
            onClick={() => onRate(item.id, rating === key ? null : key)}
            className={cn(
              "px-2.5 py-1 rounded-full text-xs border transition-colors",
              rating === key ? tone : "border-border text-text-dim hover:border-text-dim"
            )}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

function scopeLabel(affinity) {
  return affinity.target_id
    .replace("comp:", "")
    .replace("team:", "")
    .replace("player:", "")
    .replace("coach:", "");
}

function PreviewPanel({ preview }) {
  if (!preview) return null;
  const scopes = preview.scope_affinities ?? [];
  const events = preview.event_affinities ?? [];
  return (
    <SectionCard title="מה המערכת למדה עליך" icon={Sparkles}>
      {scopes.length === 0 ? (
        <p className="text-xs text-text-dim">דרג עוד כותרות כדי שנוכל להסיק העדפות (נדרשות לפחות שתיים לכל תחום).</p>
      ) : (
        <div className="space-y-2 text-xs">
          <div className="flex flex-wrap gap-1.5">
            {scopes.map((a) => (
              <span key={`${a.scope}:${a.target_id}`}
                className="px-2 py-0.5 rounded-full border border-border bg-surface-2 text-text-secondary">
                {scopeLabel(a)}: {LEVEL_LABELS[a.level] ?? a.level}
              </span>
            ))}
          </div>
          {events.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {events.map((e) => (
                <span key={`${e.scope_ref}:${e.event_type}`}
                  className="px-2 py-0.5 rounded-full border border-border/60 bg-surface-1 text-text-dim">
                  {e.event_type} @ {scopeLabel({ target_id: e.scope_ref ?? "כללי" })}: {e.delta > 0 ? `+${e.delta}` : e.delta}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </SectionCard>
  );
}

export default function Calibration() {
  const { isBackendMode, activeProfileId, consumerSession, refreshProfiles, refreshFeed } = useApp();
  const [items, setItems] = useState([]);
  const [version, setVersion] = useState(null);
  const [ratings, setRatings] = useState({});
  const [preview, setPreview] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [applied, setApplied] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isBackendMode) return;
    setIsLoading(true);
    Promise.all([
      getCalibrationItems(),
      (consumerSession
        ? getMeCalibrationResponses()
        : getCalibrationResponses(activeProfileId)
      ).catch(() => ({ ratings: {} })),
    ])
      .then(([data, saved]) => {
        setItems(data.items);
        setVersion(data.version);
        setRatings(saved.ratings ?? {});
      })
      .catch((err) => setError(err.message))
      .finally(() => setIsLoading(false));
  }, [isBackendMode, activeProfileId, consumerSession]);

  const ratedCount = Object.keys(ratings).length;

  const handleRate = (id, rating) => {
    setApplied(false);
    setRatings((prev) => {
      const next = { ...prev };
      if (rating === null) delete next[id];
      else next[id] = rating;
      return next;
    });
  };

  const handlePreview = async () => {
    setError(null);
    try {
      setPreview(await previewCalibration(ratings));
    } catch (err) {
      setError(err.message);
    }
  };

  const handleApply = async () => {
    setIsApplying(true);
    setError(null);
    try {
      if (consumerSession) {
        await applyMeCalibration(ratings);
      } else {
        await applyCalibration(activeProfileId, ratings);
      }
      setApplied(true);
      refreshProfiles?.();
      refreshFeed?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsApplying(false);
    }
  };

  const bySport = useMemo(() => {
    const groups = {};
    for (const item of items) (groups[item.sport] ??= []).push(item);
    return groups;
  }, [items]);

  if (!isBackendMode) {
    return (
      <div className="max-w-4xl space-y-4">
        <PageHeader title="כיול העדפות" icon={SlidersHorizontal} subtitle="דרג כותרות סינתטיות כדי שנלמד מה מעניין אותך" />
        <SectionCard title="כיול העדפות" icon={SlidersHorizontal}>
          <p className="text-xs text-text-secondary">
            כיול ההעדפות רץ בבקאנד (מודל ההעדפות v2) וזמין רק במצב שרת.
          </p>
          <p className="text-xs text-text-dim mt-1">
            הפעל <span className="font-mono">VITE_DATA_MODE=backend</span> כדי לכייל את הפרופיל.
          </p>
        </SectionCard>
      </div>
    );
  }

  return (
    <div className="max-w-4xl space-y-4">
      <PageHeader
        title="כיול העדפות"
        icon={SlidersHorizontal}
        subtitle={
          <>
            דרג כותרות סינתטיות — המערכת תסיק פרופיל העדפות ותשמור אותו לפרופיל{" "}
            <span className="text-signal-high">{activeProfileId}</span>
            {version != null && <span className="text-text-dim"> · גרסת מאגר {version}</span>}
          </>
        }
      />

      {error && (
        <div className={consoleAlert("error")}>
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <StatCard label="דורגו" value={`${ratedCount}/${items.length}`} tone={ratedCount > 0 ? "high" : "neutral"} />
        <StatCard label="תחומים במאגר" value={Object.keys(bySport).length} />
        <StatCard label="סטטוס" value={applied ? "נשמר" : "טיוטה"} tone={applied ? "high" : "neutral"} />
      </div>

      <div className="flex gap-2 flex-wrap items-center">
        <button onClick={handlePreview} disabled={ratedCount === 0} className={consoleButton("secondary")}>
          <Sparkles size={13} /> תצוגה מקדימה
        </button>
        <button onClick={handleApply} disabled={isApplying || ratedCount === 0} className={consoleButton("primary")}>
          {isApplying
            ? <><RefreshCw size={13} className="animate-spin" /> שומר...</>
            : <><CheckCircle2 size={13} /> שמור לפרופיל</>}
        </button>
        {applied && (
          <span className="text-xs text-signal-high flex items-center gap-1">
            <CheckCircle2 size={12} /> ההעדפות נשמרו — הפיד מחושב לפיהן
          </span>
        )}
      </div>

      <PreviewPanel preview={preview} />

      {isLoading ? (
        <div className="flex items-center gap-2 text-xs text-text-dim">
          <RefreshCw size={12} className="animate-spin" /> טוען כותרות...
        </div>
      ) : (
        Object.entries(bySport).map(([sport, sportItems]) => (
          <div key={sport} className="space-y-2">
            <h2 className="text-sm font-semibold text-text-secondary">{SPORT_LABELS[sport] ?? sport}</h2>
            {sportItems.map((item) => (
              <ItemCard key={item.id} item={item} rating={ratings[item.id]} onRate={handleRate} />
            ))}
          </div>
        ))
      )}
    </div>
  );
}
