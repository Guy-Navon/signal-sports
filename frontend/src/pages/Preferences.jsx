import React, { useState } from "react";
import { useApp } from "@/context/AppContext";
import { Settings, User, VolumeX } from "lucide-react";
import { cn } from "@/lib/utils";
import TopicCard from "@/components/preferences/TopicCard";
import LearnedAdjustmentsPanel from "@/components/preferences/LearnedAdjustmentsPanel";
import InterestsManager from "@/components/interests/InterestsManager";
import PageHeader from "@/components/shared/PageHeader";
import DeskIntro from "@/components/shared/DeskIntro";

// Consumer sessions manage explicit interests (issue #83) and no longer see
// the legacy topics tab (that model stays for ops/local demo contexts).
const CONSUMER_TABS = [
  { id: "interests", label: "תחומי עניין" },
  { id: "muted", label: "מושתק" },
  { id: "learned", label: "נלמד" },
];

const LEGACY_TABS = [
  { id: "topics", label: "נושאים ועדיפויות" },
  { id: "entities", label: "ישויות במעקב" },
  { id: "muted", label: "מושתק" },
  { id: "learned", label: "נלמד" },
];

export default function Preferences() {
  const {
    activeProfile, activeProfileId, updateProfile, isBackendMode,
    consumerSession, refreshProfiles, refreshFeed,
  } = useApp();
  const tabs = consumerSession ? CONSUMER_TABS : LEGACY_TABS;
  const [activeTab, setActiveTab] = useState(tabs[0].id);

  const handleMuteSource = (sourceId) => {
    const updated = {
      ...activeProfile,
      mutedSources: activeProfile.mutedSources.includes(sourceId)
        ? activeProfile.mutedSources.filter((s) => s !== sourceId)
        : [...activeProfile.mutedSources, sourceId],
    };
    updateProfile(activeProfileId, updated);
  };

  const handleMuteTopic = (topicId) => {
    const updated = {
      ...activeProfile,
      mutedTopics: activeProfile.mutedTopics.includes(topicId)
        ? activeProfile.mutedTopics.filter((t) => t !== topicId)
        : [...activeProfile.mutedTopics, topicId],
    };
    updateProfile(activeProfileId, updated);
  };

  // Consumer profiles are built on explicit ProfileV2 follows (#83); the
  // legacy topic counts describe ops/demo profiles only.
  const explicitFollows = (activeProfile?.profileV2?.scope_affinities || [])
    .filter((a) => a.source === "explicit" && a.level >= 0).length;
  const topicCount = consumerSession ? explicitFollows : (activeProfile?.topics?.length || 0);
  const entityCount = activeProfile?.followedEntities?.length || 0;
  const mutedCount =
    (activeProfile?.mutedTopics?.length || 0) + (activeProfile?.mutedSources?.length || 0);

  return (
    <div className="max-w-2xl space-y-5">
      <PageHeader
        title="העדפות"
        icon={Settings}
        subtitle={
          <>
            פרופיל: <span className="text-signal-high">{activeProfile?.displayName}</span> · סוג: {activeProfile?.profileType}
          </>
        }
      />

      <DeskIntro kicker="מה המערכת יודעת">
        {consumerSession ? (
          <>
            הפרופיל שלך בנוי מ־<span className="text-foreground font-medium">{topicCount}</span>{" "}
            תחומי עניין במעקב
          </>
        ) : (
          <>
            הפרופיל שלך בנוי מ־<span className="text-foreground font-medium">{topicCount}</span> נושאים
            במעקב, <span className="text-foreground font-medium">{entityCount}</span> ישויות ספציפיות
          </>
        )}
        {mutedCount > 0 && (
          <>
            , ו־<span className="text-foreground font-medium">{mutedCount}</span> נושאים ומקורות
            מושתקים
          </>
        )}
        . שינויים כאן נכנסים לתוקף מיד בפיד.
      </DeskIntro>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors",
              activeTab === tab.id
                ? "text-signal-high border-signal-high"
                : "text-text-dim border-transparent hover:text-text-secondary"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "interests" && consumerSession && (
        <InterestsManager
          onSaved={() => {
            refreshProfiles?.();
            refreshFeed?.();
          }}
        />
      )}

      {activeTab === "topics" && (
        <div>
          {activeProfile?.topics?.map((topic) => (
            <TopicCard key={topic.topicId} topic={topic} />
          ))}
        </div>
      )}

      {activeTab === "entities" && (
        <div className="space-y-4">
          <div>
            <p className="text-xs text-text-dim mb-3 flex items-center gap-1">
              <User size={11} /> ישויות שאני עוקב אחריהן (שחקנים, קבוצות, אנשים)
            </p>
            {activeProfile?.followedEntities?.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {activeProfile.followedEntities.map((entity) => (
                  <div
                    key={entity}
                    className="flex items-center gap-2 bg-signal-high/10 border border-signal-high/30 rounded-full px-3 py-1.5"
                  >
                    <span className="text-sm text-signal-high">{entity}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-text-dim">לא מוגדרות ישויות</p>
            )}
          </div>

          <p className="text-xs text-text-secondary leading-relaxed border-s-2 border-signal-ai/30 ps-3">
            <span className="text-signal-ai/90 font-medium">הבדל חשוב: </span>
            כשנושא במצב <span className="text-foreground">followed_entities_only</span>, רק כתבות
            שמכילות ישויות אלה יוצגו. לעומת זאת, כשנושא במצב{" "}
            <span className="text-foreground">all</span>, הישויות הן בונוס אך לא תנאי הכרחי.
          </p>
        </div>
      )}

      {activeTab === "muted" && (
        <div className="space-y-4">
          <MutedList
            title="נושאים מושתקים"
            items={activeProfile?.mutedTopics}
            emptyLabel="אין נושאים מושתקים"
            onToggle={handleMuteTopic}
          />
          <MutedList
            title="מקורות מושתקים"
            items={activeProfile?.mutedSources}
            emptyLabel="אין מקורות מושתקים"
            onToggle={handleMuteSource}
          />
        </div>
      )}

      {activeTab === "learned" && (
        <LearnedAdjustmentsPanel />
      )}
    </div>
  );
}

function MutedList({ title, items, emptyLabel, onToggle }) {
  return (
    <div>
      <p className="text-sm font-medium text-text-secondary mb-2 flex items-center gap-1">
        <VolumeX size={14} /> {title}
      </p>
      {items?.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <button
              key={item}
              onClick={() => onToggle(item)}
              className="flex items-center gap-1.5 bg-signal-hidden/10 border border-signal-hidden/25 rounded-full px-3 py-1.5 text-xs text-signal-hidden hover:bg-signal-hidden/20 transition-colors"
            >
              <VolumeX size={11} />
              {item}
            </button>
          ))}
        </div>
      ) : (
        <p className="text-xs text-text-dim">{emptyLabel}</p>
      )}
    </div>
  );
}
