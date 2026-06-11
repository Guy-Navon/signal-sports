import React, { useState } from "react";
import { useApp } from "@/context/AppContext";
import { Settings, ChevronDown, ChevronUp, User, Tag, Volume2, VolumeX } from "lucide-react";
import DecisionBadge from "@/components/feed/DecisionBadge";

const MODE_LABELS = {
  all: "הכל — כל הכתבות",
  major_only: "חשוב בלבד — רק כתבות משמעותיות",
  followed_entities_only: "ישויות בלבד — רק ישויות שאני עוקב אחריהן",
  muted: "מושתק",
  titles_only: "כותרות בלבד — רק ז׳אנרים ספציפיים",
  high_importance_only: "חשיבות גבוהה בלבד"
};

const DECISION_OPTIONS = ["push", "high_feed", "feed", "low_feed", "hidden"];
const DECISION_LABELS = {
  push: "Push",
  high_feed: "חשוב",
  feed: "רגיל",
  low_feed: "נמוך",
  hidden: "מוסתר"
};

function TopicCard({ topic }) {
  const [expanded, setExpanded] = useState(false);
  const modeLabel = MODE_LABELS[topic.mode] || topic.mode;

  return (
    <div className="border border-gray-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full text-right p-4 flex items-start justify-between gap-3 hover:bg-gray-800/30 transition-colors"
      >
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="font-medium text-white text-sm">{topic.label}</span>
            <span className="text-[10px] bg-gray-800 border border-gray-700 rounded px-2 py-0.5 text-gray-400">
              עדיפות: {topic.priority}
            </span>
          </div>
          <p className="text-xs text-gray-500">{modeLabel}</p>
          {topic.leagues && topic.leagues.length > 0 && (
            <p className="text-xs text-gray-600 mt-0.5">
              ליגות: {topic.leagues.join(", ")}
            </p>
          )}
        </div>
        {expanded ? <ChevronUp size={16} className="text-gray-600 mt-1 flex-shrink-0" /> : <ChevronDown size={16} className="text-gray-600 mt-1 flex-shrink-0" />}
      </button>

      {expanded && (
        <div className="border-t border-gray-800 p-4 space-y-4">
          {/* Mode explanation */}
          <div className="bg-gray-800/40 rounded-lg p-3">
            <p className="text-xs text-gray-400">
              <span className="text-gray-300 font-medium">מצב: </span>
              {modeLabel}
            </p>
            {topic.mode === "followed_entities_only" && (
              <p className="text-xs text-amber-400/80 mt-1">
                ⚠️ נושא זה יציג רק כתבות שמכילות את הישויות שאתה עוקב אחריהן
              </p>
            )}
          </div>

          {/* Entities */}
          {topic.entities && topic.entities.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-2 flex items-center gap-1">
                <Tag size={11} />
                ישויות
              </p>
              <div className="flex flex-wrap gap-1.5">
                {topic.entities.map(e => (
                  <span key={e} className="text-xs bg-gray-800 border border-gray-700 rounded-full px-2.5 py-1 text-gray-300">
                    {e}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Event Rules */}
          {topic.eventRules && Object.keys(topic.eventRules).length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-2">כללי אירוע</p>
              <div className="space-y-1">
                {Object.entries(topic.eventRules).map(([eventType, decision]) => (
                  <div key={eventType} className="flex items-center justify-between py-1 border-b border-gray-800/50">
                    <span className="text-xs text-gray-400 font-mono">{eventType}</span>
                    <DecisionBadge decision={decision} size="xs" />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Preferences() {
  const { activeProfile, activeProfileId, updateProfile } = useApp();
  const [activeTab, setActiveTab] = useState("topics");

  const handleMuteSource = (sourceId) => {
    const updated = {
      ...activeProfile,
      mutedSources: activeProfile.mutedSources.includes(sourceId)
        ? activeProfile.mutedSources.filter(s => s !== sourceId)
        : [...activeProfile.mutedSources, sourceId]
    };
    updateProfile(activeProfileId, updated);
  };

  const handleMuteTopic = (topicId) => {
    const updated = {
      ...activeProfile,
      mutedTopics: activeProfile.mutedTopics.includes(topicId)
        ? activeProfile.mutedTopics.filter(t => t !== topicId)
        : [...activeProfile.mutedTopics, topicId]
    };
    updateProfile(activeProfileId, updated);
  };

  return (
    <div className="space-y-4 pb-20 md:pb-6 max-w-2xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Settings size={18} className="text-gray-400" />
            העדפות
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            פרופיל: <span className="text-emerald-400">{activeProfile?.displayName}</span>
            {" · "}
            סוג: {activeProfile?.profileType}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        {[
          { id: "topics", label: "נושאים ועדיפויות" },
          { id: "entities", label: "ישויות במעקב" },
          { id: "muted", label: "מושתק" }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? "text-emerald-400 border-emerald-400"
                : "text-gray-500 border-transparent hover:text-gray-300"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Topics Tab */}
      {activeTab === "topics" && (
        <div className="space-y-3">
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-3">
            <p className="text-xs text-gray-500 leading-relaxed">
              כל נושא מגדיר: עדיפות, מצב (all / major_only / followed_entities_only / titles_only), ישויות, וכללי אירוע.
              שינויים ייכנסו לתוקף מיד.
            </p>
          </div>
          {activeProfile?.topics?.map(topic => (
            <TopicCard key={topic.topicId} topic={topic} />
          ))}
        </div>
      )}

      {/* Entities Tab */}
      {activeTab === "entities" && (
        <div className="space-y-4">
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-4">
            <p className="text-xs text-gray-500 mb-3 flex items-center gap-1">
              <User size={11} />
              ישויות שאני עוקב אחריהן (שחקנים, קבוצות, אנשים)
            </p>
            {activeProfile?.followedEntities?.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {activeProfile.followedEntities.map(entity => (
                  <div key={entity} className="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/30 rounded-full px-3 py-1.5">
                    <span className="text-sm text-emerald-300">{entity}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-600">לא מוגדרות ישויות</p>
            )}
          </div>

          <div className="bg-amber-950/20 border border-amber-900/40 rounded-lg p-3">
            <p className="text-xs text-amber-400/80">
              <span className="font-medium">הבדל חשוב:</span>{" "}
              כשנושא במצב <span className="text-emerald-300">followed_entities_only</span>,
              רק כתבות שמכילות ישויות אלה יוצגו.
              לעומת זאת, כשנושא במצב <span className="text-emerald-300">all</span>,
              הישויות הן בונוס אך לא תנאי הכרחי.
            </p>
          </div>
        </div>
      )}

      {/* Muted Tab */}
      {activeTab === "muted" && (
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium text-gray-300 mb-2 flex items-center gap-1">
              <VolumeX size={14} />
              נושאים מושתקים
            </p>
            {activeProfile?.mutedTopics?.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {activeProfile.mutedTopics.map(t => (
                  <button
                    key={t}
                    onClick={() => handleMuteTopic(t)}
                    className="flex items-center gap-1.5 bg-red-900/20 border border-red-900/40 rounded-full px-3 py-1.5 text-xs text-red-400 hover:bg-red-900/30"
                  >
                    <VolumeX size={11} />
                    {t}
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-600">אין נושאים מושתקים</p>
            )}
          </div>

          <div>
            <p className="text-sm font-medium text-gray-300 mb-2 flex items-center gap-1">
              <VolumeX size={14} />
              מקורות מושתקים
            </p>
            {activeProfile?.mutedSources?.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {activeProfile.mutedSources.map(s => (
                  <button
                    key={s}
                    onClick={() => handleMuteSource(s)}
                    className="flex items-center gap-1.5 bg-red-900/20 border border-red-900/40 rounded-full px-3 py-1.5 text-xs text-red-400 hover:bg-red-900/30"
                  >
                    <VolumeX size={11} />
                    {s}
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-600">אין מקורות מושתקים</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}