import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Compass, RefreshCw, AlertCircle, ChevronLeft } from "lucide-react";
import { cn } from "@/lib/utils";
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
import PageHeader from "@/components/shared/PageHeader";
import { consoleAlert, consoleButton } from "@/components/ops/consoleStyles";

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

export default function InterestSelection() {
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
      navigate(inOnboarding ? "/calibration" : "/", { replace: true });
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
      navigate("/calibration", { replace: true });
    } catch (err) {
      setError(err?.message || "משהו השתבש");
      setIsSaving(false);
    }
  }

  return (
    <div className="max-w-4xl space-y-4">
      {inOnboarding && (
        <div className="flex items-center justify-between rounded-lg border border-border bg-surface-1 px-4 py-2.5">
          <p className="text-xs text-text-secondary">
            שלב {stepIndex + 1} מתוך {STEPS.length} · אפשר לדלג — הכול ניתן לעריכה
            אחר כך בהעדפות.
          </p>
          <button
            type="button"
            onClick={skipAll}
            disabled={isSaving}
            className="text-xs text-text-secondary hover:text-foreground underline underline-offset-4 transition-colors flex-shrink-0"
          >
            דלגו על הבחירה
          </button>
        </div>
      )}

      <PageHeader
        title={step.title}
        icon={Compass}
        subtitle={step.subtitle}
      />

      {/* Step dots */}
      <div className="flex gap-1.5">
        {STEPS.map((s, i) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setStepIndex(i)}
            aria-label={s.title}
            className={cn(
              "h-1.5 rounded-full transition-all",
              i === stepIndex ? "w-8 bg-signal-high" : "w-4 bg-border hover:bg-text-dim",
            )}
          />
        ))}
      </div>

      {error && (
        <div className={consoleAlert("error")}>
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center gap-2 text-xs text-text-dim">
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

      <div className="flex items-center justify-between pt-2">
        <button
          type="button"
          onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
          disabled={stepIndex === 0}
          className="text-xs text-text-secondary hover:text-foreground disabled:opacity-40 transition-colors"
        >
          חזרה
        </button>
        <div className="flex items-center gap-3">
          <span className="text-xs text-text-dim">
            {followCount > 0 ? `${followCount} תחומים במעקב` : "עוד לא נבחר כלום"}
          </span>
          {isLast ? (
            <button
              onClick={saveAndContinue}
              disabled={isSaving || !canContinue}
              className={consoleButton("primary")}
            >
              {isSaving
                ? <><RefreshCw size={13} className="animate-spin" /> שומר...</>
                : <>המשך לכיול <ChevronLeft size={13} /></>}
            </button>
          ) : (
            <button
              onClick={() => setStepIndex((i) => i + 1)}
              className={consoleButton("primary")}
            >
              הבא <ChevronLeft size={13} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
