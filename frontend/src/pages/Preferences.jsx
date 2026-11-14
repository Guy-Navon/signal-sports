import React, { lazy, useEffect, useRef } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/context/AuthContext";
import { onboardingState } from "@/context/onboardingFlow";
import { Settings, User, VolumeX } from "lucide-react";
import TopicCard from "@/components/preferences/TopicCard";
import LearnedAdjustmentsPanel from "@/components/preferences/LearnedAdjustmentsPanel";
import InterestsManager from "@/components/interests/InterestsManager";
import InterestSelection from "@/pages/InterestSelection";
import LazyBoundary from "@/components/shell/LazyBoundary";
import { PREFERENCE_TABS, adjacentTab, preferenceTab } from "@/components/preferences/preferencesRoutes";
import { PersonalizationHeader as PageHeader } from "@/components/preferences/PersonalizationLayout";
import "@/components/preferences/preferences.css";

const Calibration = lazy(() => import("@/pages/Calibration"));

export default function Preferences() {
  const {
    activeProfile, activeProfileId, updateProfile,
    consumerSession, refreshProfiles, refreshFeed,
  } = useApp();
  const auth = useAuth();
  const location = useLocation();
  const tabRefs = useRef({});
  const activeTab = preferenceTab(location.pathname);
  const inOnboarding = consumerSession && onboardingState(auth) !== "ACTIVE";

  useEffect(() => {
    tabRefs.current[activeTab]?.scrollIntoView({ behavior: "instant", block: "nearest", inline: "nearest" });
  }, [activeTab]);

  if (!activeTab) return <Navigate replace to={`/preferences${location.search}${location.hash}`} />;

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
            פרופיל: <bdi dir="auto">{activeProfile?.displayName}</bdi> · סוג: <bdi dir="auto">{activeProfile?.profileType}</bdi>
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
      <div className="sg-preferences__tabs" role="tablist" aria-label="סוגי העדפות" aria-orientation="horizontal">
        {PREFERENCE_TABS.map((tab) => (
          <Link
            key={tab.id}
            ref={(node) => { tabRefs.current[tab.id] = node; }}
            id={`sg-preferences-tab-${tab.id}`}
            to={`${tab.path}${location.search}`}
            role="tab"
            tabIndex={activeTab === tab.id ? 0 : -1}
            aria-selected={activeTab === tab.id}
            aria-controls="sg-preferences-content"
            onKeyDown={(event) => {
              const next = adjacentTab(tab.id, event.key);
              if (next) {
                event.preventDefault();
                tabRefs.current[next]?.focus();
              } else if (event.key === " ") {
                event.preventDefault();
                event.currentTarget.click();
              }
            }}
          >
            {tab.label}
          </Link>
        ))}
      </div>

      <div id="sg-preferences-content" className="sg-preferences__panel" role="tabpanel" tabIndex={0} aria-labelledby={`sg-preferences-tab-${activeTab}`}>
      {activeTab === "following" && inOnboarding && <InterestSelection embedded />}
      {activeTab === "following" && consumerSession && !inOnboarding && (
        <InterestsManager
          onSaved={() => {
            refreshProfiles?.();
            refreshFeed?.();
          }}
        />
      )}

      {activeTab === "following" && !consumerSession && (
        <div>
          {!activeProfile?.topics?.length && <p className="sg-form-empty">אין עדיין העדפות. בחירת תחומי עניין מחכה לכם במסך תחומי העניין.</p>}
          {activeProfile?.topics?.map((topic) => (
            <TopicCard key={topic.topicId} topic={topic} />
          ))}
        </div>
      )}

      {activeTab === "following" && !consumerSession && (
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
      {activeTab === "calibration" && <LazyBoundary><Calibration embedded /></LazyBoundary>}
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
