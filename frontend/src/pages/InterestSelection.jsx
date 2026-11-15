import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Compass, RefreshCw, AlertCircle, ChevronLeft } from "lucide-react";
import {
  completeMeInterests,
  getMeInterests,
  getTaxonomyCatalog,
  putMeInterests,
} from "@/api/client";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/context/AuthContext";
import { onboardingState } from "@/context/onboardingFlow";
import {
  buildPutPayload,
  documentToState,
} from "@/components/interests/interestsModel";
import InterestPicker from "@/components/interests/InterestPicker";
import EventPresetControls from "@/components/interests/EventPresetControls";
import { PersonalizationHeader as PageHeader } from "@/components/preferences/PersonalizationLayout";


// Explicit interest selection (issue #82, docs/INTERESTS.md) — stage 1 of
// EXPLICIT SELECTION → CALIBRATION → LEARNING. A four-step stepper during
// onboarding; also reachable later (Preferences owns post-onboarding
// editing, #83). Deterministic and taxonomy-backed: every choice is a
// canonical id, no LLM anywhere.

const STEPS = [
  { id: "sports", title: "אילו ענפים מעניינים אתכם?", subtitle: "בחירה רחבה — סיקור שקט של כל הענף. את העוצמה מוסיפים בשלבים הבאים." },
  { id: "competitions", title: "אילו ליגות וטורנירים?", subtitle: "הקישו למעקב; כוכב = \"אל תפספס לי\". ליגות שאינן זמינות יסומנו בקרוב." },
  { id: "teams", title: "קבוצות ושחקנים", subtitle: "אפשר גם לחפש ישירות — מעקב אחרי קבוצה לא מוסיף אוטומטית את הליגה או הענף." },
  { id: "events", title: "אילו סוגי חדשות?", subtitle: "כיוון גס וגלובלי — את הניואנסים לכל ליגה נלמד בכיול ומהפידבק שלכם." },
];

export default function InterestSelection({ embedded = false }) {
  const navigate = useNavigate();
  const auth = useAuth();
  const { consumerSession } = useApp();
  const inOnboarding = consumerSession && onboardingState(auth) !== "ACTIVE";

  const [catalog, setCatalog] = useState(null);
  const [follows, setFollows] = useState([]);
  const [eventPreferences, setEventPreferences] = useState({});
  const [stepIndex, setStepIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([getTaxonomyCatalog(), getMeInterests().catch(() => null)])
      .then(([cat, doc]) => {
        setCatalog(cat);
        if (doc) {
          const state = documentToState(doc);
          setFollows(state.follows);
          setEventPreferences(state.eventPreferences);
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setIsLoading(false));
  }, []);

  const step = STEPS[stepIndex];
  const isLast = stepIndex === STEPS.length - 1;
  const followCount = follows.length;

  const canContinue = useMemo(() => {
    // Nothing is strictly required; the primary button is always live.
    return true;
  }, []);

  async function saveAndContinue() {
    setIsSaving(true);
    setError(null);
    try {
      await putMeInterests(buildPutPayload(follows, eventPreferences));
      await auth.refreshSession();
      navigate(inOnboarding ? "/preferences/calibration" : "/", { replace: true });
    } catch (err) {
      setError(err?.message || "שמירת ההעדפות נכשלה");
      setIsSaving(false);
    }
  }

  async function skipAll() {
    setIsSaving(true);
    setError(null);
    try {
      await completeMeInterests();
      await auth.refreshSession();
      navigate("/preferences/calibration", { replace: true });
    } catch (err) {
      setError(err?.message || "משהו השתבש");
      setIsSaving(false);
    }
  }

  return (
    <div className={embedded ? "sg-preferences__section" : "sg-personalization"}>
      {inOnboarding && (
        <div className="sg-form-banner">
          <p className="sg-form-note">
            שלב {stepIndex + 1} מתוך {STEPS.length} · אפשר לדלג — הכול ניתן לעריכה
            אחר כך בהעדפות.
          </p>
          <button
            type="button"
            onClick={skipAll}
            disabled={isSaving}
            className="sg-form-link"
          >
            דלגו על הבחירה
          </button>
        </div>
      )}

      <PageHeader
        level={embedded ? 2 : 1}
        title={step.title}
        icon={Compass}
        subtitle={step.subtitle}
      />

      {/* Full-size step targets, with the active step exposed to assistive technology. */}
      <div className="sg-interest-steps" role="group" aria-label="שלבי בחירת תחומי עניין">
        {STEPS.map((s, i) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setStepIndex(i)}
            aria-label={s.title}
            aria-current={i === stepIndex ? "step" : undefined}
          >
            {i + 1}. {s.id === "sports" ? "ענפים" : s.id === "competitions" ? "ליגות" : s.id === "teams" ? "קבוצות" : "חדשות"}
          </button>
        ))}
      </div>

      {error && (
        <div className="sg-form-error" role="alert">
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {isLoading ? (
        <div className="sg-form-note sg-form-actions" role="status">
          <RefreshCw size={12} className="animate-spin" /> טוען את הקטלוג...
        </div>
      ) : step.id === "events" ? (
        <EventPresetControls value={eventPreferences} onChange={setEventPreferences} />
      ) : (
        <InterestPicker
          catalog={catalog}
          follows={follows}
          onFollowsChange={setFollows}
          variant="onboarding"
          step={step.id}
        />
      )}

      <div className="sg-form-actions sg-form-actions--between">
        <button
          type="button"
          onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
          disabled={stepIndex === 0}
          className="sg-form-button"
        >
          חזרה
        </button>
        <div className="sg-form-actions">
          <span className="sg-form-note" role="status">
            {followCount > 0 ? `${followCount} תחומים במעקב` : "עוד לא נבחר כלום"}
          </span>
          {isLast ? (
            <button
              onClick={saveAndContinue}
              disabled={isSaving || !canContinue}
              className="sg-form-button sg-form-button--primary"
            >
              {isSaving
                ? <><RefreshCw size={13} className="animate-spin" /> שומר...</>
                : <>המשך לכיול <ChevronLeft size={13} /></>}
            </button>
          ) : (
            <button
              onClick={() => setStepIndex((i) => i + 1)}
              className="sg-form-button sg-form-button--primary"
            >
              הבא <ChevronLeft size={13} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
