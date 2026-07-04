import React, { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  Zap, ThumbsUp, Minus, ThumbsDown, EyeOff,
  ChevronDown, ChevronUp, Target, RotateCcw,
  CheckCircle, ArrowLeft, Trash2
} from "lucide-react";
import { cn } from "@/lib/utils";
import { calibrationHeadlines } from "@/data/calibrationHeadlines";
import { mockArticles } from "@/data/mockArticles";
import {
  inferPreferenceDraftFromCalibration,
  RATING_LABELS_HE,
  RATINGS
} from "@/engine/calibrationEngine";
import {
  convertCalibrationDraftToUserProfile,
  previewEntityEventRules
} from "@/engine/draftToProfile";
import { scoreArticle } from "@/engine/relevanceEngine";
import { useApp } from "@/context/AppContext";
import PageHeader from "@/components/shared/PageHeader";

// ── Rating config ─────────────────────────────────────────────────────────────

const RATING_BUTTONS = [
  {
    key: RATINGS.push,
    icon: Zap,
    label: RATING_LABELS_HE[RATINGS.push],
    activeClass: "bg-signal-push/20 border-signal-push text-signal-push",
    hoverClass: "hover:border-signal-push/50 hover:text-signal-push",
  },
  {
    key: RATINGS.interesting,
    icon: ThumbsUp,
    label: RATING_LABELS_HE[RATINGS.interesting],
    activeClass: "bg-signal-high/20 border-signal-high text-signal-high",
    hoverClass: "hover:border-signal-high/50 hover:text-signal-high",
  },
  {
    key: RATINGS.neutral,
    icon: Minus,
    label: RATING_LABELS_HE[RATINGS.neutral],
    activeClass: "bg-surface-3 border-text-dim text-foreground",
    hoverClass: "hover:border-text-dim hover:text-text-secondary",
  },
  {
    key: RATINGS.not_interesting,
    icon: ThumbsDown,
    label: RATING_LABELS_HE[RATINGS.not_interesting],
    activeClass: "bg-signal-hidden/12 border-signal-hidden/50 text-signal-hidden/90",
    hoverClass: "hover:border-signal-hidden/40 hover:text-signal-hidden/80",
  },
  {
    key: RATINGS.never_show,
    icon: EyeOff,
    label: RATING_LABELS_HE[RATINGS.never_show],
    activeClass: "bg-signal-hidden/20 border-signal-hidden text-signal-hidden",
    hoverClass: "hover:border-signal-hidden/50 hover:text-signal-hidden",
  }
];

const SPORT_LABELS_HE = {
  basketball: "כדורסל",
  football: "כדורגל",
  tennis: "טניס"
};

const EVENT_TYPE_LABELS_HE = {
  negotiation: "מו״מ",
  signing: "חתימה",
  injury: "פציעה",
  candidate: "מועמד",
  interview: "ראיון",
  friendly_match: "ידידות",
  major_signing: "חתימה גדולה",
  match_result: "תוצאה",
  finals_result: "גמר",
  playoff_result: "פלייאוף",
  title_win: "אלוף",
  regular_season_result: "תוצאה רגילה",
  major_trade: "טרייד",
  star_trade: "טרייד כוכב",
  generic_preview: "תצפית",
  major_match_result: "דרבי/משחק מרכזי",
  grand_slam_winner: "זכייה גראנד סלאם",
  early_round_result: "סיבוב ראשוני",
  generic_news: "חדשות כלליות",
  major_transfer: "טרנספר ענק",
  schedule: "לו״ז",
  record: "שיא"
};

const IMPORTANCE_LABELS_HE = {
  very_high: "גבוה מאוד",
  high: "גבוה",
  medium: "בינוני",
  low: "נמוך",
  very_low: "נמוך מאוד"
};

const IMPORTANCE_COLORS = {
  very_high: "text-signal-push bg-signal-push/10 border-signal-push/30",
  high: "text-signal-high bg-signal-high/10 border-signal-high/30",
  medium: "text-signal-feed bg-signal-feed/10 border-signal-feed/30",
  low: "text-text-secondary bg-surface-3 border-border",
  very_low: "text-text-dim bg-surface-2 border-border"
};

const MODE_LABELS_HE = {
  all: "הכל",
  followed_entities_only: "ישויות בלבד",
  titles_only: "כותרות בלבד",
  major_only: "חשוב בלבד",
  high_importance_only: "חשיבות גבוהה",
  muted: "מושתק"
};

const DECISION_LABELS_HE = {
  push: "דחוף",
  high_feed: "חשוב",
  feed: "רגיל",
  low_feed: "נמוך",
  hidden: "מוסתר"
};

const DECISION_COLORS = {
  push: "text-signal-push",
  high_feed: "text-signal-high",
  feed: "text-signal-feed",
  low_feed: "text-text-dim",
  hidden: "text-signal-hidden"
};

// ── Sub-components ────────────────────────────────────────────────────────────

function HeadlineCard({ headline, currentRating, onRate }) {
  const sport = SPORT_LABELS_HE[headline.sport] || headline.sport;
  const eventType = EVENT_TYPE_LABELS_HE[headline.eventType] || headline.eventType;
  const importanceLabel = IMPORTANCE_LABELS_HE[headline.importance] || headline.importance;
  const importanceColor = IMPORTANCE_COLORS[headline.importance] || IMPORTANCE_COLORS.low;
  const isRated = !!currentRating;

  return (
    <div className={cn(
      "rounded-2xl border transition-colors bg-surface-1",
      isRated ? "border-border" : "border-border/70"
    )}>
      <div className="p-4 pb-3">
        <p className="text-sm font-medium text-foreground leading-snug mb-2.5">{headline.title}</p>

        <div className="flex flex-wrap gap-1.5">
          <span className="text-[10px] bg-surface-3 border border-border rounded-full px-2 py-0.5 text-text-secondary">{sport}</span>
          {headline.league && (
            <span className="text-[10px] bg-surface-3 border border-border rounded-full px-2 py-0.5 text-text-secondary">{headline.league}</span>
          )}
          <span className="text-[10px] bg-surface-3 border border-border rounded-full px-2 py-0.5 text-text-dim">{eventType}</span>
          <span className={cn("text-[10px] border rounded-full px-2 py-0.5", importanceColor)}>{importanceLabel}</span>
        </div>

        {headline.entities.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {headline.entities.map((e) => (
              <span key={e} className="text-[10px] text-text-dim">{e}</span>
            ))}
          </div>
        )}
      </div>

      <div className="border-t border-border px-3 py-2.5 flex gap-1.5 flex-wrap">
        {RATING_BUTTONS.map((btn) => {
          const Icon = btn.icon;
          const isActive = currentRating === btn.key;
          return (
            <button
              key={btn.key}
              onClick={() => onRate(headline.id, isActive ? null : btn.key)}
              title={btn.label}
              className={cn(
                "flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] border transition-colors",
                isActive ? btn.activeClass : cn("border-border text-text-dim", btn.hoverClass)
              )}
            >
              <Icon size={11} />
              <span className="hidden sm:inline">{btn.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function DecisionChip({ decision }) {
  return (
    <span className={cn("font-medium", DECISION_COLORS[decision] || "text-text-dim")}>
      {DECISION_LABELS_HE[decision] || decision}
    </span>
  );
}

function InferenceDraftPanel({ draft, ratedCount, onApply, sandboxExists, onReset, justApplied, sandboxFeedStats }) {
  const [expanded, setExpanded] = useState(true);

  if (ratedCount < 3) {
    return (
      <div className="border border-border rounded-2xl p-4 text-center bg-surface-1">
        <Target size={20} className="text-text-dim mx-auto mb-2" />
        <p className="text-xs text-text-dim">דרג/י לפחות 3 כותרות כדי לראות תובנות ראשוניות</p>
        <p className="text-xs text-text-dim mt-1">{ratedCount}/3 דורגו עד כה</p>
      </div>
    );
  }

  const hasTopics = draft.inferredTopics.length > 0;

  return (
    <div className="border border-border rounded-2xl overflow-hidden bg-surface-1 elevation-1">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center justify-between p-4 text-start hover:bg-surface-2/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Target size={14} className="text-signal-ai" />
          <span className="text-sm font-medium text-foreground">תובנות ראשוניות</span>
          <span className="text-[10px] text-text-dim">({ratedCount} כותרות דורגו)</span>
        </div>
        <span className="text-text-dim">{expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</span>
      </button>

      {expanded && (
        <div className="border-t border-border p-4 space-y-4">
          {hasTopics && (
            <div>
              <p className="text-xs text-text-dim mb-2">נושאים שזוהו</p>
              <div className="space-y-2">
                {draft.inferredTopics.map((topic) => {
                  const entityRulesPreview = previewEntityEventRules(topic);
                  return (
                    <div key={topic.topicKey} className="bg-surface-2 rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-xs font-medium text-foreground">{topic.label}</span>
                        <span className="text-[10px] bg-surface-3 rounded-full px-1.5 py-0.5 text-text-secondary">עדיפות {topic.priority}</span>
                        <span className="text-[10px] bg-surface-3 rounded-full px-1.5 py-0.5 text-text-secondary">{MODE_LABELS_HE[topic.mode] || topic.mode}</span>
                      </div>

                      {Object.entries(topic.eventRules).length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(topic.eventRules).map(([eventType, decision]) => (
                            <span key={eventType} className="text-[10px] flex items-center gap-1">
                              <span className="text-text-dim">{EVENT_TYPE_LABELS_HE[eventType] || eventType}</span>
                              <span className="text-text-dim">→</span>
                              <DecisionChip decision={decision} />
                            </span>
                          ))}
                        </div>
                      )}

                      {entityRulesPreview && (
                        <div className="mt-2 pt-2 border-t border-border/60">
                          <p className="text-[10px] text-text-dim mb-1">כללים ספציפיים לישות</p>
                          {Object.entries(entityRulesPreview).map(([entity, rules]) => (
                            <div key={entity} className="flex flex-wrap items-center gap-1">
                              <span className="text-[10px] text-signal-high/80 font-medium">{entity}:</span>
                              {Object.entries(rules).map(([eventType, decision]) => (
                                <span key={eventType} className="text-[10px] flex items-center gap-1">
                                  <span className="text-text-dim">{EVENT_TYPE_LABELS_HE[eventType] || eventType}</span>
                                  <span className="text-text-dim">→</span>
                                  <DecisionChip decision={decision} />
                                </span>
                              ))}
                            </div>
                          ))}
                        </div>
                      )}

                      <p className="text-[10px] text-text-dim mt-1.5">{topic.reasoning.join(" · ")}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {draft.followedEntities.length > 0 && (
            <div>
              <p className="text-xs text-text-dim mb-1.5">ישויות שזוהו כרלוונטיות</p>
              <div className="flex flex-wrap gap-1.5">
                {draft.followedEntities.map((e) => (
                  <span key={e} className="text-[11px] bg-signal-high/10 border border-signal-high/30 rounded-full px-2.5 py-1 text-signal-high">{e}</span>
                ))}
              </div>
            </div>
          )}

          {draft.mutedCandidates.length > 0 && (
            <div>
              <p className="text-xs text-text-dim mb-1.5">מועמדים להשתקה</p>
              <div className="flex flex-wrap gap-1.5">
                {[...new Set(draft.mutedCandidates)].map((s) => (
                  <span key={s} className="text-[11px] bg-signal-hidden/10 border border-signal-hidden/25 rounded-full px-2.5 py-1 text-signal-hidden">
                    {SPORT_LABELS_HE[s] || s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {draft.reasoning.length > 0 && (
            <div className="border-t border-border pt-3">
              {draft.reasoning.map((line, i) => (
                <p key={i} className="text-[10px] text-text-dim leading-relaxed">{line}</p>
              ))}
            </div>
          )}

          <div className="border-t border-border pt-3 space-y-2">
            {justApplied && (
              <div className="flex items-center gap-2 p-3 bg-signal-high/10 border border-signal-high/30 rounded-lg">
                <CheckCircle size={14} className="text-signal-high shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-signal-high">הפרופיל המכויל הופעל. גיא ומעריץ דני לא השתנו.</p>
                </div>
                <Link to="/" className="flex items-center gap-1 text-xs text-signal-high hover:text-signal-high/80 transition-colors shrink-0">
                  עבור לפיד
                  <ArrowLeft size={11} />
                </Link>
              </div>
            )}

            {justApplied && sandboxFeedStats && (
              <div className="bg-surface-2 border border-border rounded-lg p-3 space-y-2">
                <p className="text-[10px] text-text-dim font-medium">תוצאות בדיקה</p>
                <div className="flex flex-wrap gap-x-3 gap-y-1">
                  <span className="text-[10px] text-text-secondary">נושאים: <span className="text-foreground">{sandboxFeedStats.topicCount}</span></span>
                  <span className="text-[10px] text-text-secondary">ישויות: <span className="text-foreground">{sandboxFeedStats.entityCount}</span></span>
                  <span className="text-[10px] text-text-secondary">מושתקים: <span className="text-foreground">{sandboxFeedStats.mutedCount}</span></span>
                  <span className={cn("text-[10px] font-medium",
                    sandboxFeedStats.visibleCount === 0 ? "text-signal-hidden"
                    : sandboxFeedStats.visibleCount >= 10 ? "text-signal-high"
                    : "text-signal-push"
                  )}>
                    נראים: {sandboxFeedStats.visibleCount}/{sandboxFeedStats.totalCount}
                  </span>
                </div>

                {sandboxFeedStats.visibleCount > 0 && (
                  <div>
                    <p className="text-[10px] text-text-dim mb-1">כותרות מובילות</p>
                    <div className="space-y-1">
                      {sandboxFeedStats.topVisible.map((a) => (
                        <div key={a.id} className="flex items-start gap-1.5">
                          <DecisionChip decision={a.decision} />
                          <span className="text-[10px] text-text-secondary leading-tight">{a.title}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {sandboxFeedStats.visibleCount === 0 && sandboxFeedStats.topHiddenReasons.length > 0 && (
                  <div>
                    <p className="text-[10px] text-signal-hidden mb-1">⚠️ אפס כתבות נראות — סיבות הסתרה</p>
                    <div className="space-y-1">
                      {sandboxFeedStats.topHiddenReasons.map((item, i) => (
                        <div key={i} className="text-[10px] text-text-dim leading-tight">
                          <span className="text-text-secondary">{item.title}</span>
                          {item.reason && <span className="text-text-dim"> — {item.reason}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {!justApplied && (
              <button
                onClick={onApply}
                disabled={!hasTopics}
                className={cn(
                  "w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border text-xs transition-colors",
                  hasTopics
                    ? "border-signal-high/50 bg-signal-high/10 text-signal-high hover:bg-signal-high/20"
                    : "border-border text-text-dim cursor-not-allowed"
                )}
              >
                <CheckCircle size={12} />
                החל על פרופיל בדיקה
              </button>
            )}

            {sandboxExists && (
              <button
                onClick={onReset}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-lg border border-border text-text-dim text-xs hover:border-text-dim hover:text-text-secondary transition-colors"
              >
                <Trash2 size={11} />
                אפס פרופיל בדיקה
              </button>
            )}

            <p className="text-[10px] text-text-dim text-center">
              הפרופיל המכויל הוא פרופיל נפרד — פרופילי גיא ומעריץ דני אינם משתנים
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const SPORT_FILTERS = [
  { id: "all", label: "הכל" },
  { id: "basketball", label: "כדורסל" },
  { id: "football", label: "כדורגל" },
  { id: "tennis", label: "טניס" }
];

export default function Calibration() {
  const { applySandboxProfile, resetSandboxProfile, sandboxProfile } = useApp();
  const [ratings, setRatings] = useState({});
  const [sportFilter, setSportFilter] = useState("all");
  const [justApplied, setJustApplied] = useState(false);

  const ratedCount = Object.keys(ratings).length;
  const total = calibrationHeadlines.length;

  const filteredHeadlines = useMemo(() => {
    if (sportFilter === "all") return calibrationHeadlines;
    return calibrationHeadlines.filter((h) => h.sport === sportFilter);
  }, [sportFilter]);

  const draft = useMemo(
    () => inferPreferenceDraftFromCalibration(ratings, calibrationHeadlines),
    [ratings]
  );

  const handleRate = (id, rating) => {
    setRatings((prev) => {
      if (rating === null) {
        const next = { ...prev };
        delete next[id];
        return next;
      }
      return { ...prev, [id]: rating };
    });
    setJustApplied(false);
  };

  const handleClear = () => {
    setRatings({});
    setJustApplied(false);
  };

  const handleApply = () => {
    const profile = convertCalibrationDraftToUserProfile(draft);
    applySandboxProfile(profile);
    setJustApplied(true);
  };

  const handleReset = () => {
    resetSandboxProfile();
    setJustApplied(false);
  };

  const sandboxFeedStats = useMemo(() => {
    if (!justApplied) return null;
    const profile = convertCalibrationDraftToUserProfile(draft);
    const scored = mockArticles.map((a) => {
      const result = scoreArticle(a, profile);
      return {
        id: a.id,
        title: a.title,
        decision: result.decision,
        lastReason: result.reasoning[result.reasoning.length - 1] ?? ""
      };
    });
    const visible = scored.filter((s) => s.decision !== "hidden");
    const hidden = scored.filter((s) => s.decision === "hidden");
    return {
      topicCount: profile.topics.length,
      entityCount: profile.followedEntities.length,
      mutedCount: profile.mutedTopics.length,
      visibleCount: visible.length,
      totalCount: scored.length,
      topVisible: visible.slice(0, 5),
      topHiddenReasons: visible.length === 0
        ? hidden.slice(0, 5).map((s) => ({ title: s.title, reason: s.lastReason }))
        : []
    };
  }, [justApplied, draft]);

  const progressPercent = total > 0 ? Math.round((ratedCount / total) * 100) : 0;

  return (
    <div className="max-w-2xl space-y-4">
      <PageHeader
        title="כיוונון העדפות"
        icon={Target}
        subtitle="דרג/י כותרות ספורטיביות מדומות — המערכת תלמד מה מעניין אותך"
      >
        {ratedCount > 0 && (
          <button
            onClick={handleClear}
            className="flex items-center gap-1.5 text-xs text-text-dim hover:text-text-secondary transition-colors"
          >
            <RotateCcw size={12} />
            איפוס
          </button>
        )}
      </PageHeader>

      {/* Progress */}
      <div className="bg-surface-1 border border-border rounded-[10px] p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-text-secondary">
            <span className="text-foreground font-medium">{ratedCount}</span> / {total} כותרות דורגו
          </span>
          <span className="text-xs text-text-dim">{progressPercent}%</span>
        </div>
        <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
          <div className="h-full bg-signal-high rounded-full transition-all duration-300" style={{ width: `${progressPercent}%` }} />
        </div>
      </div>

      {/* Sport filter chips */}
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
        {SPORT_FILTERS.map((filter) => (
          <button
            key={filter.id}
            onClick={() => setSportFilter(filter.id)}
            className={cn(
              "flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-colors border",
              sportFilter === filter.id
                ? "bg-signal-high/15 border-signal-high/40 text-signal-high"
                : "bg-surface-1 border-border text-text-dim hover:border-text-dim hover:text-text-secondary"
            )}
          >
            {filter.label}
            {filter.id !== "all" && (
              <span className="ms-1 text-text-dim">
                ({calibrationHeadlines.filter((h) => h.sport === filter.id).length})
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Rating legend */}
      <div className="bg-surface-1 border border-border rounded-[10px] px-3 py-2">
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {RATING_BUTTONS.map((btn) => {
            const Icon = btn.icon;
            return (
              <span key={btn.key} className="flex items-center gap-1 text-[10px] text-text-dim">
                <Icon size={10} />
                {btn.label}
              </span>
            );
          })}
        </div>
      </div>

      {/* Headline cards */}
      <div className="space-y-3">
        {filteredHeadlines.map((headline) => (
          <HeadlineCard
            key={headline.id}
            headline={headline}
            currentRating={ratings[headline.id]}
            onRate={handleRate}
          />
        ))}
      </div>

      {/* Inference draft panel */}
      <div className="sticky bottom-4 md:static md:bottom-auto">
        <InferenceDraftPanel
          draft={draft}
          ratedCount={ratedCount}
          onApply={handleApply}
          sandboxExists={!!sandboxProfile}
          onReset={handleReset}
          justApplied={justApplied}
          sandboxFeedStats={sandboxFeedStats}
        />
      </div>
    </div>
  );
}
