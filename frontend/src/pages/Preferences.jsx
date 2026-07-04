import React, { useState } from "react";
import { useApp } from "@/context/AppContext";
import { Settings, User, VolumeX } from "lucide-react";
import { cn } from "@/lib/utils";
import TopicCard from "@/components/preferences/TopicCard";
import PageHeader from "@/components/shared/PageHeader";

const TABS = [
  { id: "topics", label: "נושאים ועדיפויות" },
  { id: "entities", label: "ישויות במעקב" },
  { id: "muted", label: "מושתק" },
];

export default function Preferences() {
  const { activeProfile, activeProfileId, updateProfile } = useApp();
  const [activeTab, setActiveTab] = useState("topics");

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

  return (
    <div className="max-w-2xl space-y-4">
      <PageHeader
        title="העדפות"
        icon={Settings}
        subtitle={
          <>
            פרופיל: <span className="text-signal-high">{activeProfile?.displayName}</span> · סוג: {activeProfile?.profileType}
          </>
        }
      />

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {TABS.map((tab) => (
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

      {activeTab === "topics" && (
        <div className="space-y-3">
          <div className="bg-surface-1 border border-border rounded-[10px] p-3">
            <p className="text-xs text-text-dim leading-relaxed">
              כל נושא מגדיר: עדיפות, מצב (all / major_only / followed_entities_only / titles_only), ישויות, וכללי אירוע.
              שינויים ייכנסו לתוקף מיד.
            </p>
          </div>
          {activeProfile?.topics?.map((topic) => (
            <TopicCard key={topic.topicId} topic={topic} />
          ))}
        </div>
      )}

      {activeTab === "entities" && (
        <div className="space-y-4">
          <div className="bg-surface-1 border border-border rounded-2xl p-4">
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

          <div className="bg-signal-push/8 border border-signal-push/25 rounded-2xl p-3">
            <p className="text-xs text-signal-push/90">
              <span className="font-medium">הבדל חשוב:</span> כשנושא במצב{" "}
              <span className="text-signal-high">followed_entities_only</span>, רק כתבות שמכילות ישויות אלה יוצגו.
              לעומת זאת, כשנושא במצב <span className="text-signal-high">all</span>, הישויות הן בונוס אך לא תנאי הכרחי.
            </p>
          </div>
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
