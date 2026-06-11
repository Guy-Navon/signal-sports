import React, { useState, useMemo } from "react";
import { useApp } from "@/context/AppContext";
import FeedCard from "@/components/feed/FeedCard";
import { Rss } from "lucide-react";

const FILTER_CHIPS = [
  { id: "all", label: "הכל" },
  { id: "push", label: "דורש תשומת לב" },
  { id: "high_feed", label: "חשוב" },
  { id: "maccabi", label: "מכבי" },
  { id: "basketball", label: "כדורסל" },
  { id: "NBA", label: "NBA" },
  { id: "international", label: "מקורות מחו״ל" }
];

const DECISION_RANK = { hidden: 0, low_feed: 1, feed: 2, high_feed: 3, push: 4 };

export default function Feed() {
  const { feedItems, activeProfile } = useApp();
  const [activeFilter, setActiveFilter] = useState("all");

  // Only show non-hidden items in the main feed
  const visibleItems = useMemo(() => {
    return feedItems.filter(item => {
      const decision = item.score?.decision;
      return decision && decision !== "hidden";
    });
  }, [feedItems]);

  // Apply filter chips
  const filteredItems = useMemo(() => {
    if (activeFilter === "all") return visibleItems;

    return visibleItems.filter(item => {
      if (activeFilter === "push") return item.score?.decision === "push";
      if (activeFilter === "high_feed") return item.score?.decision === "high_feed";

      if (activeFilter === "maccabi") {
        const entities = item.entities || [];
        const tags = item.tags || [];
        return (
          entities.some(e => e.toLowerCase().includes("maccabi")) ||
          tags.some(t => t.includes("מכבי"))
        );
      }

      if (activeFilter === "basketball") return item.sport === "basketball";
      if (activeFilter === "NBA") return item.league === "NBA";

      if (activeFilter === "international") {
        const intlSources = ["sportando", "eurohoops"];
        if (item.type === "cluster") {
          return item.sources?.some(s => intlSources.includes(s));
        }
        return intlSources.includes(item.source);
      }

      return true;
    });
  }, [visibleItems, activeFilter]);

  const pushCount = visibleItems.filter(i => i.score?.decision === "push").length;
  const highCount = visibleItems.filter(i => i.score?.decision === "high_feed").length;

  return (
    <div className="space-y-4 pb-20 md:pb-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">פיד אישי</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            {visibleItems.length} פריטים רלוונטיים עבור {activeProfile?.displayName}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {pushCount > 0 && (
            <div className="flex items-center gap-1.5 bg-amber-500/10 border border-amber-500/30 rounded-full px-3 py-1">
              <div className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
              <span className="text-xs text-amber-300">{pushCount} חשובים</span>
            </div>
          )}
        </div>
      </div>

      {/* Filter Chips */}
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
        {FILTER_CHIPS.map(chip => (
          <button
            key={chip.id}
            onClick={() => setActiveFilter(chip.id)}
            className={`flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-all border ${
              activeFilter === chip.id
                ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-300"
                : "bg-gray-800/80 border-gray-700 text-gray-400 hover:border-gray-600 hover:text-gray-300"
            }`}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-2 text-center">
        {[
          { label: "דורש תשומת לב", count: visibleItems.filter(i => i.score?.decision === "push").length, color: "text-amber-400" },
          { label: "חשוב", count: visibleItems.filter(i => i.score?.decision === "high_feed").length, color: "text-emerald-400" },
          { label: "רגיל", count: visibleItems.filter(i => i.score?.decision === "feed").length, color: "text-blue-400" },
          { label: "נמוך", count: visibleItems.filter(i => i.score?.decision === "low_feed").length, color: "text-gray-500" }
        ].map(stat => (
          <div key={stat.label} className="bg-gray-900/50 rounded-lg px-2 py-2 border border-gray-800">
            <div className={`text-lg font-bold ${stat.color}`}>{stat.count}</div>
            <div className="text-[10px] text-gray-600">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Feed Items */}
      {filteredItems.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Rss size={32} className="text-gray-700 mb-3" />
          <p className="text-gray-500 text-sm">אין פריטים תואמים לסינון הנוכחי</p>
          <button
            onClick={() => setActiveFilter("all")}
            className="mt-3 text-xs text-emerald-400 hover:text-emerald-300"
          >
            הצג הכל
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredItems.map(item => (
            <FeedCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}