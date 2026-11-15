import React, { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/context/AuthContext";
import { firstUnansweredItemId, onboardingState } from "@/context/onboardingFlow";
import { useNavigate } from "react-router-dom";
import { SlidersHorizontal, RefreshCw, AlertCircle, CheckCircle2, Sparkles } from "lucide-react";
import {
  getCalibrationItems,
  getMeCalibrationItems,
  previewCalibration,
  applyCalibration,
  getCalibrationResponses,
  applyMeCalibration,
  getMeCalibrationResponses,
  saveMeCalibrationResponses,
  completeMeOnboarding,
} from "@/api/client";
import { PersonalizationHeader as PageHeader, PersonalizationSection as SectionCard, PersonalizationStat as StatCard } from "@/components/preferences/PersonalizationLayout";
import SignalStrength from "@/components/signal-ui/SignalStrength";
import AffinityLevel from "@/components/preferences/AffinityLevel";
import CalibrationSummary from "@/components/preferences/CalibrationSummary";
// Share the stream row's type, spacing, kicker and why styles with SignalFeedView.
import "@/components/feed/signal/signal-feed.css";
import "./calibration.css";

/**
 * Calibration V2 (issue #33) — backend-owned flow: the versioned dataset,
 * the hierarchical inference and the persistent apply all live in the
 * backend. This page only collects ratings and renders the results; there
 * is no frontend inference and no frontend-only sandbox state anymore.
 */

const RATING_BUTTONS = [
  { key: "push", label: "תעדכן אותי מיד", decision: "push" },
  { key: "interesting", label: "מעניין", decision: "high_feed" },
  { key: "neutral", label: "סבבה, לא קריטי", decision: "feed" },
  { key: "not_interesting", label: "לא מעניין", decision: "low_feed" },
  { key: "never_show", label: "אל תראה לי כאלה", decision: null },
];

const SPORT_LABELS = { basketball: "כדורסל", football: "כדורגל", tennis: "טניס" };

function ItemCard({ item, rating, onRate }) {
  return (
    // id: the resume anchor — "opens at the first unanswered item" (#52)
    <article id={`cal-item-${item.id}`} className="sg-row sg-calibration-row">
      <div className="sg-row__by"><bdi dir="auto">{SPORT_LABELS[item.sport] ?? item.sport}</bdi><span>· כותרת לדוגמה</span></div>
      <h3 className="sg-row__title" dir="auto">{item.title}</h3>
      <p className="sg-row__why sg-why"><b>למה כאן: </b>דוגמה לכיול ההעדפות שלך. איך תרצה לקבל כותרות כאלה?</p>
      <div className="sg-calibration-ratings" role="group" aria-label={`דירוג: ${item.title}`}>
        {RATING_BUTTONS.map(({ key, label, decision }) => (
          <button
            key={key}
            onClick={() => onRate(item.id, rating === key ? null : key)}
            className="sg-form-button"
            aria-label={label}
            aria-pressed={rating === key}
          >
            {decision && <SignalStrength decision={decision} />}{label}
          </button>
        ))}
      </div>
    </article>
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
        <p className="sg-form-note">דרג עוד כותרות כדי שנוכל להסיק העדפות (נדרשות לפחות שתיים לכל תחום).</p>
      ) : (
        <div className="space-y-2">
          <div className="sg-form-list">
            {scopes.map((a) => (
              <span key={`${a.scope}:${a.target_id}`}
                className="sg-calibration-affinity">
                <bdi dir="auto">{scopeLabel(a)}</bdi>: <AffinityLevel level={a.level} />
              </span>
            ))}
          </div>
          {events.length > 0 && (
            <div className="sg-form-list">
              {events.map((e) => (
                <span key={`${e.scope_ref}:${e.event_type}`}
                  className="sg-calibration-affinity sg-form-note">
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

export default function Calibration({ embedded = false }) {
  const { isBackendMode, activeProfileId, consumerSession, refreshProfiles, refreshFeed } = useApp();
  const auth = useAuth();
  const navigate = useNavigate();
  // Onboarding context (PR 4, #52): while onboarding is incomplete this page
  // IS the onboarding flow — it offers the skip path and, on apply, hands the
  // user their first personalized feed.
  const inOnboarding =
    consumerSession && onboardingState(auth) !== "ACTIVE";
  const [resumeAnchor, setResumeAnchor] = useState(null);
  const [items, setItems] = useState([]);
  const [version, setVersion] = useState(null);
  const [ratings, setRatings] = useState({});
  const [preview, setPreview] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [appliedResult, setAppliedResult] = useState(null);
  const applyButtonRef = useRef(null);
  const returnToRatings = useRef(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!appliedResult && returnToRatings.current) {
      returnToRatings.current = false;
      applyButtonRef.current?.focus();
    }
  }, [appliedResult]);

  useEffect(() => {
    if (!isBackendMode) return;
    setIsLoading(true);
    Promise.all([
      // Interest-aware selection for consumers (#81: ~10-14 items scoped to
      // explicit interests); the admin/ops path keeps the full dataset.
      consumerSession ? getMeCalibrationItems() : getCalibrationItems(),
      (consumerSession
        ? getMeCalibrationResponses()
        : getCalibrationResponses(activeProfileId)
      ).catch(() => ({ ratings: {} })),
    ])
      .then(([data, saved]) => {
        setItems(data.items);
        setVersion(data.version);
        setRatings(saved.ratings ?? {});
        // Resume-awareness (#52): open at the first unanswered item when
        // returning mid-calibration (same or different device).
        if (consumerSession && Object.keys(saved.ratings ?? {}).length > 0) {
          setResumeAnchor(firstUnansweredItemId(data.items, saved.ratings));
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setIsLoading(false));
  }, [isBackendMode, activeProfileId, consumerSession]);

  const ratedCount = Object.keys(ratings).length;

  useEffect(() => {
    if (!resumeAnchor) return;
    const el = document.getElementById(`cal-item-${resumeAnchor}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [resumeAnchor]);

  const handleRate = (id, rating) => {
    setAppliedResult(null);
    // A preview describes the ratings it was computed from; once they change
    // it is stale and must not be read as current (#447).
    setPreview(null);
    setRatings((prev) => {
      const next = { ...prev };
      if (rating === null) delete next[id];
      else next[id] = rating;
      return next;
    });
    // Server-side per-item persistence (#52): abandoning mid-calibration
    // loses nothing; resume works cross-device. A cleared rating is sent as
    // null, which deletes the saved response (#446). Fire-and-forget — a lost
    // rating is re-sent on apply (which saves every rating); a lost clear is
    // not, so that item can come back rated on the next visit.
    if (consumerSession) {
      saveMeCalibrationResponses({ [id]: rating }).catch(() => {});
    }
  };

  const handleSkipOnboarding = async () => {
    try {
      await completeMeOnboarding();
      await auth.refreshSession();
    } catch {
      // non-fatal — the guard will simply keep the user here
    }
    navigate("/", { replace: true });
  };

  const handlePreview = async () => {
    setIsPreviewing(true);
    setError(null);
    try {
      setPreview(await previewCalibration(ratings));
    } catch (err) {
      setError(err.message);
    } finally {
      setIsPreviewing(false);
    }
  };

  const handleApply = async () => {
    setIsApplying(true);
    setError(null);
    try {
      const result = consumerSession
        ? await applyMeCalibration(ratings)
        : await applyCalibration(activeProfileId, ratings);
      setAppliedResult(result);
      refreshProfiles?.();
      refreshFeed?.();
      if (inOnboarding) {
        // Apply still completes onboarding. Show the saved levels before the
        // user continues to the feed from the summary (#492).
        await auth.refreshSession();
      }
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
      <div className={embedded ? "sg-preferences__section sg-calibration" : "sg-personalization sg-calibration"}>
        {embedded
          ? <p className="sg-form-note">דרג כותרות לדוגמה כדי שנלמד מה מעניין אותך.</p>
          : <PageHeader title="כיול העדפות" icon={SlidersHorizontal} subtitle="דרג כותרות סינתטיות כדי שנלמד מה מעניין אותך" />}
        <SectionCard>
          <p className="sg-form-note">
            כיול ההעדפות רץ בבקאנד (מודל ההעדפות v2) וזמין רק במצב שרת.
          </p>
          <p className="sg-form-note">
            הפעל <span className="font-mono">VITE_DATA_MODE=backend</span> כדי לכייל את הפרופיל.
          </p>
        </SectionCard>
      </div>
    );
  }

  return (
    <div className={embedded ? "sg-preferences__section sg-calibration" : "sg-personalization sg-calibration"}>
      {inOnboarding && (
        <div className="sg-form-banner">
          <p className="sg-form-note">
            אפשר לעצור בכל שלב — התשובות נשמרות וממשיכים מכל מכשיר.
          </p>
          <button
            type="button"
            onClick={handleSkipOnboarding}
            className="sg-form-link"
          >
            דלגו בינתיים
          </button>
        </div>
      )}
      {embedded ? <p className="sg-form-note">דרג כותרות לדוגמה כדי שנלמד מה מעניין אותך.</p> : <PageHeader
        title="כיול העדפות"
        icon={SlidersHorizontal}
        subtitle={
          <>
            דרג כותרות סינתטיות — המערכת תסיק פרופיל העדפות ותשמור אותו{" "}
            {consumerSession
              ? <span className="sg-calibration__profile">לפרופיל שלך</span>
              : <span className="sg-calibration__profile">לפרופיל {activeProfileId}</span>}
            {version != null && <span className="sg-form-note"> · גרסת מאגר {version}</span>}
          </>
        }
      />}

      {error && (
        <div className="sg-form-error" role="alert">
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <div className="sg-form-stats">
        <StatCard label="דורגו" value={`${ratedCount}/${items.length}`} />
        <StatCard label="תחומים במאגר" value={Object.keys(bySport).length} />
        <StatCard label="סטטוס" value={appliedResult ? "נשמר" : "טיוטה"} />
      </div>

      <p className="sg-form-success sg-calibration__completion" role="status" aria-atomic="true">
        {!appliedResult && items.length > 0 && ratedCount === items.length
          ? "כל הכותרות דורגו. אפשר לשמור לפרופיל או לעדכן את הדירוגים."
          : ""}
      </p>

      {appliedResult ? (
        <CalibrationSummary result={appliedResult} onContinueRating={() => {
          returnToRatings.current = true;
          setAppliedResult(null);
        }} />
      ) : <>
      <div className="sg-form-actions">
        <button onClick={handlePreview} disabled={isPreviewing || ratedCount === 0} aria-busy={isPreviewing} className="sg-form-button">
          {isPreviewing ? <><RefreshCw size={13} className="animate-spin" /> מכין תצוגה...</> : <><Sparkles size={13} /> תצוגה מקדימה</>}
        </button>
        <button ref={applyButtonRef} onClick={handleApply} disabled={isApplying || ratedCount === 0} className="sg-form-button sg-form-button--primary">
          {isApplying
            ? <><RefreshCw size={13} className="animate-spin" /> שומר...</>
            : <><CheckCircle2 size={13} /> שמור לפרופיל</>}
        </button>
      </div>

      {!isLoading && items.length === 0 && !error && <p className="sg-form-empty" role="status">אין כרגע כותרות לכיול.</p>}
      <PreviewPanel preview={preview} />

      {isLoading ? (
        <div className="sg-form-note sg-form-actions" role="status">
          <RefreshCw size={12} className="animate-spin" /> טוען כותרות...
        </div>
      ) : (
        Object.entries(bySport).map(([sport, sportItems]) => (
          <div key={sport} className="space-y-2">
            <h2 className="sg-form-heading">{SPORT_LABELS[sport] ?? sport}</h2>
            <div className="sg-stream">
              {sportItems.map((item) => (
                <ItemCard key={item.id} item={item} rating={ratings[item.id]} onRate={handleRate} />
              ))}
            </div>
          </div>
        ))
      )}
      </>}
    </div>
  );
}
