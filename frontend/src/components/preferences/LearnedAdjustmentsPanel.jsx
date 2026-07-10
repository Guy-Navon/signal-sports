import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, AlertCircle, RotateCcw, GraduationCap } from "lucide-react";
import {
  getLearningState,
  getMeLearningState,
  resetLearning,
  resetMeLearning,
} from "@/api/client";
import { useApp } from "@/context/AppContext";
import { cn } from "@/lib/utils";

/** Learned adjustments (issue #34): derived from the user's feedback event
 * log, each individually resettable. Backend mode only — learning is a
 * backend derivation over persisted feedback events.
 *
 * Identity boundary (#54 review, HIGH-1): this is a CONSUMER product panel.
 * Under a consumer session it reads/resets ONLY the authenticated account's
 * learning via the session-derived /api/me routes — it takes no identity
 * prop, so QA view-as state cannot leak in. The legacy explicit-target calls
 * remain solely for the pre-auth local/bypass QA behavior. */
export default function LearnedAdjustmentsPanel() {
  const { isBackendMode, consumerSession, activeProfileId } = useApp();
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // consumerSession is AppContext's isConsumerSession(view) — the same
  // predicate learningSurface() (unit-tested) applies: consumer → /me.
  const useMe = consumerSession;

  const load = useCallback(() => {
    if (!isBackendMode || (!useMe && !activeProfileId)) return;
    setLoading(true);
    setError(null);
    (useMe ? getMeLearningState() : getLearningState(activeProfileId))
      .then(setState)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [useMe, activeProfileId, isBackendMode]);

  useEffect(() => { load(); }, [load]);

  const handleReset = async (feature) => {
    const payload = {
      kind: feature.kind,
      target_id: feature.target_id,
      scope_ref: feature.scope_ref,
      event_type: feature.event_type,
    };
    try {
      if (useMe) await resetMeLearning(payload);
      else await resetLearning(activeProfileId, payload);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  if (!isBackendMode) {
    return (
      <p className="text-xs text-text-secondary">
        התאמות נלמדות זמינות רק במצב שרת — הלמידה נגזרת מיומן המשובים בבקאנד.
      </p>
    );
  }
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-text-dim">
        <RefreshCw size={12} className="animate-spin" /> טוען התאמות נלמדות...
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-start gap-2 text-xs text-signal-push">
        <AlertCircle size={12} className="mt-0.5 flex-shrink-0" /> {error}
      </div>
    );
  }
  if (!state) return null;

  const active = state.features.filter((f) => f.active);
  const pending = state.features.filter((f) => !f.active);

  return (
    <div className="space-y-4">
      <p className="text-xs text-text-dim flex items-center gap-1">
        <GraduationCap size={12} />
        התאמות שנלמדו מהמשובים שלך בפיד — כל אחת ניתנת לאיפוס. לחיצה בודדת לעולם לא משנה את הפרופיל.
      </p>

      {active.length === 0 && pending.length === 0 && (
        <p className="text-xs text-text-dim">אין עדיין למידה — תן משוב על כתבות בפיד.</p>
      )}

      {active.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs font-medium text-text-secondary">פעילות</div>
          {active.map((f, i) => (
            <div key={i}
              className={cn(
                "flex items-center justify-between gap-2 rounded-[10px] border px-3 py-2",
                f.direction > 0
                  ? "border-signal-high/30 bg-signal-high/5"
                  : "border-signal-hidden/30 bg-signal-hidden/5"
              )}
            >
              <div className="text-xs text-text-secondary">
                <span className="px-1.5 py-0.5 me-2 rounded-full bg-surface-3 text-text-dim">נלמד</span>
                {f.explanation}
              </div>
              <button
                onClick={() => handleReset(f)}
                title="אפס למידה זו"
                className="flex items-center gap-1 text-xs text-text-dim hover:text-signal-push transition-colors flex-shrink-0"
              >
                <RotateCcw size={11} /> אפס
              </button>
            </div>
          ))}
        </div>
      )}

      {pending.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs font-medium text-text-dim">בצבירה (עדיין לא משפיעות)</div>
          {pending.map((f, i) => (
            <div key={i} className="text-xs text-text-dim bg-surface-2 border border-border rounded-[10px] px-3 py-2">
              {f.explanation}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
