import React from "react";
import { useApp } from "@/context/AppContext";
import { Database } from "lucide-react";
import IngestionPanel from "@/components/ops/IngestionPanel";
import NotificationsPanel from "@/components/ops/NotificationsPanel";
import SchedulerPanel from "@/components/ops/SchedulerPanel";
import BenchmarkPanel from "@/components/ops/BenchmarkPanel";
import SourceToggleCard from "@/components/ops/SourceToggleCard";
import StatCard from "@/components/shared/StatCard";
import PageHeader from "@/components/shared/PageHeader";

export default function Sources() {
  const { sources, toggleSource, isBackendMode, refreshFeed } = useApp();

  const enabledCount = sources.filter((s) => s.enabled).length;
  const rssCount = sources.filter((s) => s.sourceType === "rss").length;
  const heCount = sources.filter((s) => s.language === "he").length;

  return (
    <div className="max-w-4xl space-y-5">
      <PageHeader title="מקורות" icon={Database} subtitle={`${enabledCount}/${sources.length} מקורות פעילים`} />

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="מקורות פעילים" value={`${enabledCount}/${sources.length}`} tone="high" />
        <StatCard label="ערוצי RSS" value={rssCount} tone="feed" />
        <StatCard label="מקורות עברית" value={heCount} />
        <StatCard label="מצב נתונים" value={isBackendMode ? "שרת" : "מקומי"} tone={isBackendMode ? "high" : "neutral"} />
      </div>

      {/* Ops panels (backend mode surfaces live data; local shows the explanation) */}
      <SchedulerPanel isBackendMode={isBackendMode} onFeedRefresh={refreshFeed} />
      <NotificationsPanel isBackendMode={isBackendMode} />
      <IngestionPanel isBackendMode={isBackendMode} onFeedRefresh={refreshFeed} />
      <BenchmarkPanel isBackendMode={isBackendMode} />

      {/* Source registry */}
      <div className="space-y-2">
        <h2 className="text-sm font-semibold text-text-secondary">רשימת מקורות</h2>
        {sources.map((source) => (
          <SourceToggleCard key={source.id} source={source} onToggle={toggleSource} />
        ))}
      </div>
    </div>
  );
}
