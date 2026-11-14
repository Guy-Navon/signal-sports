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
  SOURCE_LABELS,
  buildPutPayload,
  displayNameFor,
  documentToState,
  nonExplicitEntries,
} from "@/components/interests/interestsModel";
import InterestPicker from "@/components/interests/InterestPicker";
import EventPresetControls from "@/components/interests/EventPresetControls";
import AffinityLevel from "@/components/preferences/AffinityLevel";
import { PersonalizationSection as SectionCard } from "@/components/preferences/PersonalizationLayout";


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
      <div className="sg-form-note sg-form-actions" role="status">
        <RefreshCw size={12} className="animate-spin" /> טוען תחומי עניין...
      </div>
    );
  }

  return (
    <div className="sg-interests-manager space-y-5">
      {error && (
        <div className="sg-form-error" role="alert">
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {follows.length === 0 && <p className="sg-form-empty">אין עדיין תחומי עניין במעקב. בחרו ענף, ליגה, קבוצה או שחקן כדי להתחיל.</p>}
      <InterestPicker
        catalog={catalog}
        follows={follows}
        onFollowsChange={(next) => { setFollows(next); setSaved(false); }}
        variant="manage"
      />

      <div className="space-y-2">
        <h3 className="sg-form-heading">
          העדפות כלליות לסוגי חדשות
        </h3>
        <EventPresetControls
          value={eventPreferences}
          onChange={(next) => { setEventPreferences(next); setSaved(false); }}
        />
      </div>

      <div className="sg-form-actions">
        <button
          onClick={save}
          disabled={isSaving}
          className="sg-form-button sg-form-button--primary"
        >
          {isSaving
            ? <><RefreshCw size={13} className="animate-spin" /> שומר...</>
            : <><CheckCircle2 size={13} /> שמור תחומי עניין</>}
        </button>
        {saved && (
          <span className="sg-form-success" role="status">
            <CheckCircle2 size={12} /> נשמר — הפיד מחושב לפי הבחירות
          </span>
        )}
      </div>

      {derived.length > 0 && (
        <SectionCard title="העדפות שנגזרו מכיול ומהתנהגות" icon={Sparkles}>
          <p className="sg-form-note">
            הרשומות האלה נוצרו מהכיול ומהפידבק שלך — הן לא נערכות ידנית.
            בחירה מפורשת שלך תמיד גוברת עליהן; הן מתעדכנות מכיול חוזר ומהמשוב
            בפיד.
          </p>
          <div className="sg-form-list">
            {derived.map((entry) => (
              <span
                key={`${entry.source}:${entry.scope}:${entry.target_id}`}
                className="sg-derived-interest"
              >
                <bdi dir="auto">{displayNameFor(catalog, entry.scope, entry.target_id)}</bdi>
                {": "}
                <AffinityLevel level={entry.level} />
                <span className="sg-form-note">
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
