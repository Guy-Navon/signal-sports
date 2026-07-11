import React, { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, RefreshCw, Sparkles } from "lucide-react";
import {
  getMeInterests,
  getMeProfile,
  getTaxonomyCatalog,
  putMeInterests,
} from "@/api/client";
import { normalizeProfileFromApi } from "@/api/normalizers";
import {
  LEVEL_LABELS,
  SOURCE_LABELS,
  buildPutPayload,
  displayNameFor,
  documentToState,
  nonExplicitEntries,
} from "@/components/interests/interestsModel";
import InterestPicker from "@/components/interests/InterestPicker";
import EventPresetControls from "@/components/interests/EventPresetControls";
import SectionCard from "@/components/shared/SectionCard";
import { consoleAlert, consoleButton } from "@/components/ops/consoleStyles";

// Post-onboarding interests editing (issue #83) — the same picker
// components as onboarding (#82), flat "manage" variant. Editing writes
// through PUT /api/me/interests: only the managed explicit subset is
// replaced; calibration/learned entries (shown read-only below with
// provenance labels) and overrides/mutes always survive.
export default function InterestsManager({ onSaved }) {
  const [catalog, setCatalog] = useState(null);
  const [follows, setFollows] = useState([]);
  const [eventPreferences, setEventPreferences] = useState({});
  const [derived, setDerived] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      getTaxonomyCatalog(),
      getMeInterests(),
      getMeProfile().then(normalizeProfileFromApi).catch(() => null),
    ])
      .then(([cat, doc, profile]) => {
        setCatalog(cat);
        const state = documentToState(doc);
        setFollows(state.follows);
        setEventPreferences(state.eventPreferences);
        setDerived(nonExplicitEntries(profile?.profileV2));
      })
      .catch((err) => setError(err.message))
      .finally(() => setIsLoading(false));
  }, []);

  async function save() {
    setIsSaving(true);
    setSaved(false);
    setError(null);
    try {
      await putMeInterests(buildPutPayload(follows, eventPreferences));
      setSaved(true);
      onSaved?.();
    } catch (err) {
      setError(err?.message || "שמירת ההעדפות נכשלה");
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-text-dim">
        <RefreshCw size={12} className="animate-spin" /> טוען תחומי עניין...
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {error && (
        <div className={consoleAlert("error")}>
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <InterestPicker
        catalog={catalog}
        follows={follows}
        onFollowsChange={(next) => { setFollows(next); setSaved(false); }}
        variant="manage"
      />

      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-text-secondary">
          העדפות כלליות לסוגי חדשות
        </h3>
        <EventPresetControls
          value={eventPreferences}
          onChange={(next) => { setEventPreferences(next); setSaved(false); }}
        />
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={isSaving}
          className={consoleButton("primary")}
        >
          {isSaving
            ? <><RefreshCw size={13} className="animate-spin" /> שומר...</>
            : <><CheckCircle2 size={13} /> שמור תחומי עניין</>}
        </button>
        {saved && (
          <span className="text-xs text-signal-high flex items-center gap-1">
            <CheckCircle2 size={12} /> נשמר — הפיד מחושב לפי הבחירות
          </span>
        )}
      </div>

      {derived.length > 0 && (
        <SectionCard title="העדפות שנגזרו מכיול ומהתנהגות" icon={Sparkles}>
          <p className="text-xs text-text-dim mb-2">
            הרשומות האלה נוצרו מהכיול ומהפידבק שלך — הן לא נערכות ידנית.
            בחירה מפורשת שלך תמיד גוברת עליהן; הן מתעדכנות מכיול חוזר ומהמשוב
            בפיד.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {derived.map((entry) => (
              <span
                key={`${entry.source}:${entry.scope}:${entry.target_id}`}
                className="px-2 py-0.5 rounded-full border border-border/60 bg-surface-1 text-xs text-text-secondary"
              >
                {displayNameFor(catalog, entry.scope, entry.target_id)}
                {": "}
                {LEVEL_LABELS[entry.level] ?? entry.level}
                <span className="text-text-dim">
                  {" · "}
                  {SOURCE_LABELS[entry.source] ?? "מוגדר מראש"}
                </span>
              </span>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  );
}
