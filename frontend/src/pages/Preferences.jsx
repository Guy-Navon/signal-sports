import React, { useState } from "react";
import { useApp } from "@/context/AppContext";
import { Settings, User, VolumeX } from "lucide-react";
import TopicCard from "@/components/preferences/TopicCard";
import LearnedAdjustmentsPanel from "@/components/preferences/LearnedAdjustmentsPanel";
import InterestsManager from "@/components/interests/InterestsManager";
import { PersonalizationHeader as PageHeader } from "@/components/preferences/PersonalizationLayout";
import "@/components/preferences/preferences.css";

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
    activeProfile, activeProfileId, updateProfile,
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
    <div className="sg-personalization sg-preferences">
      <PageHeader
        title="העדפות"
        icon={Settings}
        subtitle={
          <>
            פרופיל: <bdi dir="auto">{activeProfile?.displayName}</bdi> · סוג: {activeProfile?.profileType}
          </>
        }
      />

      <p className="sg-form-note">
        {consumerSession ? (
          <>
            הפרופיל שלך בנוי מ־<span className="sg-preferences__count">{topicCount}</span>{" "}
            תחומי עניין במעקב
          </>
        ) : (
          <>
            הפרופיל שלך בנוי מ־<span className="sg-preferences__count">{topicCount}</span> נושאים
            במעקב, <span className="sg-preferences__count">{entityCount}</span> ישויות ספציפיות
          </>
        )}
        {mutedCount > 0 && (
          <>
            , ו־<span className="sg-preferences__count">{mutedCount}</span> נושאים ומקורות
            מושתקים
          </>
        )}
        . שינויים כאן נכנסים לתוקף מיד בפיד.
      </p>

      {/* Tabs */}
      <div className="sg-preferences__tabs" role="group" aria-label="סוגי העדפות">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            type="button"
            aria-pressed={activeTab === tab.id}
            aria-controls="sg-preferences-content"
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div id="sg-preferences-content">
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
          {!activeProfile?.topics?.length && <p className="sg-form-empty">אין עדיין העדפות. בחירת תחומי עניין מחכה לכם במסך תחומי העניין.</p>}
          {activeProfile?.topics?.map((topic) => (
            <TopicCard key={topic.topicId} topic={topic} />
          ))}
        </div>
      )}

      {activeTab === "entities" && (
        <div className="space-y-4">
          <div>
            <p className="sg-form-heading">
              <User size={11} /> ישויות שאני עוקב אחריהן (שחקנים, קבוצות, אנשים)
            </p>
            {activeProfile?.followedEntities?.length > 0 ? (
              <div className="sg-form-list">
                {activeProfile.followedEntities.map((entity) => (
                  <div
                    key={entity}
                    className="sg-preferences__entity"
                  >
                    <bdi dir="auto">{entity}</bdi>
                  </div>
                ))}
              </div>
            ) : (
              <p className="sg-form-empty">לא מוגדרות ישויות</p>
            )}
          </div>

          <p className="sg-form-note">
            <span className="sg-preferences__count">הבדל חשוב: </span>
            כשנושא במצב <span dir="ltr">followed_entities_only</span>, רק כתבות
            שמכילות ישויות אלה יוצגו. לעומת זאת, כשנושא במצב{" "}
            <span dir="ltr">all</span>, הישויות הן בונוס אך לא תנאי הכרחי.
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
    </div>
  );
}

function MutedList({ title, items, emptyLabel, onToggle }) {
  return (
    <div>
      <p className="sg-form-heading">
        <VolumeX size={14} /> {title}
      </p>
      {items?.length > 0 ? (
        <div className="sg-form-list">
          {items.map((item) => (
            <button
              key={item}
              onClick={() => onToggle(item)}
              className="sg-form-button"
            >
              <VolumeX size={11} />
              <bdi dir="auto">{item}</bdi>
            </button>
          ))}
        </div>
      ) : (
        <p className="sg-form-empty">{emptyLabel}</p>
      )}
    </div>
  );
}
