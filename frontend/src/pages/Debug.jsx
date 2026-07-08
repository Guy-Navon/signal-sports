import React, { useState, useMemo } from "react";
import { useApp } from "@/context/AppContext";
import { Bug, Search, GitCompare, FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";
import DebugArticleCard from "@/components/debug/DebugArticleCard";
import ProfileComparisonTable from "@/components/debug/ProfileComparisonTable";
import ShadowComparisonPanel from "@/components/debug/ShadowComparisonPanel";
import PageHeader from "@/components/shared/PageHeader";
import StatCard from "@/components/shared/StatCard";
import EmptyState from "@/components/shared/EmptyState";

const DECISION_FILTERS = [
  { id: "all", label: "הכל" },
  { id: "push", label: "Push" },
  { id: "high_feed", label: "High" },
  { id: "feed", label: "Feed" },
  { id: "low_feed", label: "Low" },
  { id: "hidden", label: "Hidden" },
];

const STAT_TILES = [
  { key: "push", label: "דורש תשומת לב", tone: "push" },
  { key: "high_feed", label: "חשוב", tone: "high" },
  { key: "feed", label: "רגיל", tone: "feed" },
  { key: "low_feed", label: "נמוך", tone: "low" },
  { key: "hidden", label: "מוסתר", tone: "hidden" },
];

export default function Debug() {
  const { debugItems, activeProfile, activeProfileId, comparisonItems, profiles, isBackendMode } = useApp();
  const [filterDecision, setFilterDecision] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState("debug");

  const filtered = useMemo(() => {
    return debugItems.filter((item) => {
      if (filterDecision !== "all" && item.score?.decision !== filterDecision) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const title = (item.type === "cluster" ? item.clusterTitle : item.title) || "";
        return (
          title.toLowerCase().includes(q) ||
          (item.sport || "").includes(q) ||
          (item.league || "").toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [debugItems, filterDecision, searchQuery]);

  const decisionCounts = useMemo(() => {
    const counts = { hidden: 0, low_feed: 0, feed: 0, high_feed: 0, push: 0 };
    debugItems.forEach((item) => {
      const d = item.score?.decision || "hidden";
      if (counts[d] !== undefined) counts[d]++;
    });
    return counts;
  }, [debugItems]);

  const hiddenCount = decisionCounts.hidden;
  const visibleCount = debugItems.length - hiddenCount;

  const tabButton = (id, active) =>
    cn(
      "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5",
      active
        ? id === "compare"
          ? "text-signal-ai border-signal-ai"
          : "text-signal-high border-signal-high"
        : "text-text-dim border-transparent hover:text-text-secondary"
    );

  return (
    <div className="max-w-4xl space-y-4">
      <PageHeader
        title="פאנל דיבאג"
        icon={Bug}
        subtitle={
          <>
            פרופיל פעיל: <span className="text-signal-high">{activeProfile?.displayName}</span> ·{" "}
            {visibleCount} מוצגים, {hiddenCount} מוסתרים
          </>
        }
      />

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        <button onClick={() => setActiveTab("debug")} className={tabButton("debug", activeTab === "debug")}>
          <Bug size={13} /> פאנל דיבאג
        </button>
        <button onClick={() => setActiveTab("compare")} className={tabButton("compare", activeTab === "compare")}>
          <GitCompare size={13} /> השוואת פרופילים
        </button>
        <button onClick={() => setActiveTab("shadow")} className={tabButton("shadow", activeTab === "shadow")}>
          <FlaskConical size={13} /> מנוע v2 (shadow)
        </button>
      </div>

      {activeTab === "shadow" && (
        <ShadowComparisonPanel userId={activeProfileId} isBackendMode={isBackendMode} />
      )}

      {activeTab === "compare" && (
        <div className="space-y-3">
          <div className="bg-signal-ai/5 border border-signal-ai/25 rounded-[10px] p-3">
            <p className="text-xs text-signal-ai/90">
              השוואה בין כל הפרופילים לכל כתבה. שורות <span className="font-medium">מודגשות</span> = פרופילים מחליטים שונה.
            </p>
          </div>
          <ProfileComparisonTable items={comparisonItems} profiles={profiles} />
        </div>
      )}

      {activeTab === "debug" && (
        <>
          <div className="grid grid-cols-5 gap-2">
            {STAT_TILES.map(({ key, label, tone }) => (
              <StatCard key={key} value={decisionCounts[key]} label={label} tone={tone} className="px-2 py-2 text-center" />
            ))}
          </div>

          {/* Filters */}
          <div className="flex gap-2 flex-wrap">
            <div className="relative flex-1 min-w-[180px]">
              <Search size={13} className="absolute end-3 top-1/2 -translate-y-1/2 text-text-dim" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="חיפוש לפי כותרת..."
                className="w-full bg-surface-2 border border-border rounded-lg ps-3 pe-8 py-2 text-xs text-foreground placeholder-text-dim focus:outline-none focus:border-signal-feed/40"
              />
            </div>
            {DECISION_FILTERS.map(({ id, label }) => (
              <button
                key={id}
                onClick={() => setFilterDecision(id)}
                className={cn(
                  "px-3 py-1.5 rounded-full text-xs font-medium border transition-colors",
                  filterDecision === id
                    ? "bg-surface-3 border-text-dim text-foreground"
                    : "bg-surface-1 border-border text-text-dim hover:border-text-dim"
                )}
              >
                {label}
                {id !== "all" && <span className="ms-1 text-text-dim">({decisionCounts[id] || 0})</span>}
              </button>
            ))}
          </div>

          <div className="bg-signal-push/5 border border-signal-push/25 rounded-[10px] p-3">
            <p className="text-xs text-signal-push/90">
              <span className="font-medium">מצב דיבאג:</span> כל הפריטים גלויים, כולל מוסתרים. לחץ על שורה לשרשרת ההחלטה המלאה.
            </p>
          </div>

          <div className="space-y-2">
            {filtered.length === 0 ? (
              <EmptyState icon={Bug} title="לא נמצאו פריטים" hint="נסה לשנות את הסינון או החיפוש." />
            ) : (
              filtered.map((item) => <DebugArticleCard key={item.id} item={item} />)
            )}
          </div>
        </>
      )}
    </div>
  );
}
