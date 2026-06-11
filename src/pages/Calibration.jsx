import React, { useState, useMemo } from "react";
import {
  Zap, ThumbsUp, Minus, ThumbsDown, EyeOff,
  ChevronDown, ChevronUp, Target, RotateCcw, Lock
} from "lucide-react";
import { calibrationHeadlines } from "@/data/calibrationHeadlines";
import {
  inferPreferenceDraftFromCalibration,
  RATING_LABELS_HE,
  RATINGS
} from "@/engine/calibrationEngine";

// ── Rating config ─────────────────────────────────────────────────────────────

const RATING_BUTTONS = [
  {
    key: RATINGS.push,
    icon: Zap,
    label: RATING_LABELS_HE[RATINGS.push],
    activeClass: "bg-amber-500/20 border-amber-400 text-amber-300",
    hoverClass: "hover:border-amber-700 hover:text-amber-400"
  },
  {
    key: RATINGS.interesting,
    icon: ThumbsUp,
    label: RATING_LABELS_HE[RATINGS.interesting],
    activeClass: "bg-emerald-500/20 border-emerald-400 text-emerald-300",
    hoverClass: "hover:border-emerald-700 hover:text-emerald-400"
  },
  {
    key: RATINGS.neutral,
    icon: Minus,
    label: RATING_LABELS_HE[RATINGS.neutral],
    activeClass: "bg-gray-600/40 border-gray-400 text-gray-200",
    hoverClass: "hover:border-gray-500 hover:text-gray-300"
  },
  {
    key: RATINGS.not_interesting,
    icon: ThumbsDown,
    label: RATING_LABELS_HE[RATINGS.not_interesting],
    activeClass: "bg-orange-900/30 border-orange-600 text-orange-300",
    hoverClass: "hover:border-orange-800 hover:text-orange-400"
  },
  {
    key: RATINGS.never_show,
    icon: EyeOff,
    label: RATING_LABELS_HE[RATINGS.never_show],
    activeClass: "bg-red-900/30 border-red-600 text-red-300",
    hoverClass: "hover:border-red-800 hover:text-red-400"
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
  very_high: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  high: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  medium: "text-blue-400 bg-blue-500/10 border-blue-500/30",
  low: "text-gray-400 bg-gray-800 border-gray-700",
  very_low: "text-gray-500 bg-gray-800/50 border-gray-800"
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

// ── Sub-components ────────────────────────────────────────────────────────────

function HeadlineCard({ headline, currentRating, onRate }) {
  const sport = SPORT_LABELS_HE[headline.sport] || headline.sport;
  const eventType = EVENT_TYPE_LABELS_HE[headline.eventType] || headline.eventType;
  const importanceLabel = IMPORTANCE_LABELS_HE[headline.importance] || headline.importance;
  const importanceColor = IMPORTANCE_COLORS[headline.importance] || IMPORTANCE_COLORS.low;
  const isRated = !!currentRating;

  return (
    <div className={`rounded-xl border transition-colors ${
      isRated ? "border-gray-700 bg-gray-900/40" : "border-gray-800 bg-gray-900/60"
    }`}>
      {/* Card header */}
      <div className="p-4 pb-3">
        <p className="text-sm font-medium text-white leading-snug mb-2.5">
          {headline.title}
        </p>

        {/* Metadata chips */}
        <div className="flex flex-wrap gap-1.5">
          <span className="text-[10px] bg-gray-800 border border-gray-700 rounded px-2 py-0.5 text-gray-400">
            {sport}
          </span>
          {headline.league && (
            <span className="text-[10px] bg-gray-800 border border-gray-700 rounded px-2 py-0.5 text-gray-400">
              {headline.league}
            </span>
          )}
          <span className="text-[10px] bg-gray-800 border border-gray-700 rounded px-2 py-0.5 text-gray-500">
            {eventType}
          </span>
          <span className={`text-[10px] border rounded px-2 py-0.5 ${importanceColor}`}>
            {importanceLabel}
          </span>
        </div>

        {/* Entities */}
        {headline.entities.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {headline.entities.map(e => (
              <span key={e} className="text-[10px] text-gray-500">
                {e}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Rating buttons */}
      <div className="border-t border-gray-800 px-3 py-2.5 flex gap-1.5 flex-wrap">
        {RATING_BUTTONS.map(btn => {
          const Icon = btn.icon;
          const isActive = currentRating === btn.key;
          return (
            <button
              key={btn.key}
              onClick={() => onRate(headline.id, isActive ? null : btn.key)}
              title={btn.label}
              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] border transition-all ${
                isActive
                  ? btn.activeClass
                  : `border-gray-700 text-gray-500 ${btn.hoverClass}`
              }`}
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

function InferenceDraftPanel({ draft, ratedCount }) {
  const [expanded, setExpanded] = useState(true);

  if (ratedCount < 3) {
    return (
      <div className="border border-gray-800 rounded-xl p-4 text-center">
        <Target size={20} className="text-gray-700 mx-auto mb-2" />
        <p className="text-xs text-gray-600">
          דרג/י לפחות 3 כותרות כדי לראות תובנות ראשוניות
        </p>
        <p className="text-xs text-gray-700 mt-1">
          {ratedCount}/3 דורגו עד כה
        </p>
      </div>
    );
  }

  const hasTopics = draft.inferredTopics.length > 0;

  return (
    <div className="border border-gray-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between p-4 text-right hover:bg-gray-800/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Target size={14} className="text-emerald-400" />
          <span className="text-sm font-medium text-white">תובנות ראשוניות</span>
          <span className="text-[10px] text-gray-500">({ratedCount} כותרות דורגו)</span>
        </div>
        {expanded ? <ChevronUp size={14} className="text-gray-600" /> : <ChevronDown size={14} className="text-gray-600" />}
      </button>

      {expanded && (
        <div className="border-t border-gray-800 p-4 space-y-4">

          {/* Inferred topics */}
          {hasTopics && (
            <div>
              <p className="text-xs text-gray-500 mb-2">נושאים שזוהו</p>
              <div className="space-y-2">
                {draft.inferredTopics.map(topic => (
                  <div key={topic.topicKey} className="bg-gray-800/40 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-xs font-medium text-gray-200">{topic.label}</span>
                      <span className="text-[10px] bg-gray-700 rounded px-1.5 py-0.5 text-gray-400">
                        עדיפות {topic.priority}
                      </span>
                      <span className="text-[10px] bg-gray-700 rounded px-1.5 py-0.5 text-gray-400">
                        {MODE_LABELS_HE[topic.mode] || topic.mode}
                      </span>
                    </div>

                    {/* Event rules */}
                    {Object.entries(topic.eventRules).length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(topic.eventRules).map(([eventType, decision]) => (
                          <span key={eventType} className="text-[10px] flex items-center gap-1">
                            <span className="text-gray-500">{EVENT_TYPE_LABELS_HE[eventType] || eventType}</span>
                            <span className="text-gray-700">→</span>
                            <DecisionChip decision={decision} />
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Reasoning */}
                    <p className="text-[10px] text-gray-600 mt-1.5">
                      {topic.reasoning.join(" · ")}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Followed entities */}
          {draft.followedEntities.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-1.5">ישויות שזוהו כרלוונטיות</p>
              <div className="flex flex-wrap gap-1.5">
                {draft.followedEntities.map(e => (
                  <span key={e} className="text-[11px] bg-emerald-500/10 border border-emerald-500/30 rounded-full px-2.5 py-1 text-emerald-300">
                    {e}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Muted candidates */}
          {draft.mutedCandidates.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-1.5">מועמדים להשתקה</p>
              <div className="flex flex-wrap gap-1.5">
                {[...new Set(draft.mutedCandidates)].map(s => (
                  <span key={s} className="text-[11px] bg-red-900/20 border border-red-900/40 rounded-full px-2.5 py-1 text-red-400">
                    {SPORT_LABELS_HE[s] || s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Global reasoning */}
          {draft.reasoning.length > 0 && (
            <div className="border-t border-gray-800 pt-3">
              {draft.reasoning.map((line, i) => (
                <p key={i} className="text-[10px] text-gray-600 leading-relaxed">{line}</p>
              ))}
            </div>
          )}

          {/* Apply draft — disabled for PR 2, future functionality */}
          <div className="border-t border-gray-800 pt-3">
            <button
              disabled
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-gray-700 text-gray-600 text-xs cursor-not-allowed"
              title="פונקציה עתידית — טרם זמין"
            >
              <Lock size={11} />
              החל עדפות על פרופיל — עתידי
            </button>
            <p className="text-[10px] text-gray-700 text-center mt-1">
              בשלב זה הניתוח הוא תצוגה מקדימה בלבד
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function DecisionChip({ decision }) {
  const colors = {
    push: "text-amber-400",
    high_feed: "text-emerald-400",
    feed: "text-blue-400",
    low_feed: "text-gray-500",
    hidden: "text-red-500"
  };
  return (
    <span className={`font-medium ${colors[decision] || "text-gray-500"}`}>
      {DECISION_LABELS_HE[decision] || decision}
    </span>
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
  const [ratings, setRatings] = useState({});
  const [sportFilter, setSportFilter] = useState("all");

  const ratedCount = Object.keys(ratings).length;
  const total = calibrationHeadlines.length;

  const filteredHeadlines = useMemo(() => {
    if (sportFilter === "all") return calibrationHeadlines;
    return calibrationHeadlines.filter(h => h.sport === sportFilter);
  }, [sportFilter]);

  const draft = useMemo(
    () => inferPreferenceDraftFromCalibration(ratings, calibrationHeadlines),
    [ratings]
  );

  const handleRate = (id, rating) => {
    setRatings(prev => {
      if (rating === null) {
        const next = { ...prev };
        delete next[id];
        return next;
      }
      return { ...prev, [id]: rating };
    });
  };

  const handleClear = () => setRatings({});

  const progressPercent = total > 0 ? Math.round((ratedCount / total) * 100) : 0;

  return (
    <div className="space-y-4 pb-24 md:pb-6 max-w-2xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Target size={18} className="text-emerald-400" />
            כיוונון העדפות
          </h1>
          <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
            דרג/י כותרות ספורטיביות מדומות — המערכת תלמד מה מעניין אותך
          </p>
        </div>
        {ratedCount > 0 && (
          <button
            onClick={handleClear}
            className="flex items-center gap-1.5 text-xs text-gray-600 hover:text-gray-400 transition-colors mt-1"
          >
            <RotateCcw size={12} />
            איפוס
          </button>
        )}
      </div>

      {/* Progress */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-gray-400">
            <span className="text-white font-medium">{ratedCount}</span>
            {" "}/{" "}{total} כותרות דורגו
          </span>
          <span className="text-xs text-gray-600">{progressPercent}%</span>
        </div>
        <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-emerald-500 rounded-full transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Sport filter chips */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {SPORT_FILTERS.map(filter => (
          <button
            key={filter.id}
            onClick={() => setSportFilter(filter.id)}
            className={`flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-all border ${
              sportFilter === filter.id
                ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-300"
                : "bg-gray-800/80 border-gray-700 text-gray-400 hover:border-gray-600 hover:text-gray-300"
            }`}
          >
            {filter.label}
            {filter.id !== "all" && (
              <span className="mr-1 text-gray-600">
                ({calibrationHeadlines.filter(h => h.sport === filter.id).length})
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Rating legend (compact) */}
      <div className="bg-gray-900/30 border border-gray-800/50 rounded-lg px-3 py-2">
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {RATING_BUTTONS.map(btn => {
            const Icon = btn.icon;
            return (
              <span key={btn.key} className="flex items-center gap-1 text-[10px] text-gray-600">
                <Icon size={10} />
                {btn.label}
              </span>
            );
          })}
        </div>
      </div>

      {/* Headline cards */}
      <div className="space-y-3">
        {filteredHeadlines.map(headline => (
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
        <InferenceDraftPanel draft={draft} ratedCount={ratedCount} />
      </div>
    </div>
  );
}
