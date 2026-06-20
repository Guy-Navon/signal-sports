import React, { useState, useMemo } from "react";
import { useApp } from "@/context/AppContext";
import DecisionBadge from "@/components/feed/DecisionBadge";
import { Bug, ChevronDown, ChevronUp, Search, GitCompare } from "lucide-react";

const DECISION_RANK = { hidden: 0, low_feed: 1, feed: 2, high_feed: 3, push: 4 };

const CLASSIFIED_BY_STYLES = {
  "rules":                              "bg-gray-800/80 text-gray-400 border-gray-700/40",
  "llm":                                "bg-blue-950/60 text-blue-300 border-blue-700/40",
  "llm+rules_guardrail":                "bg-yellow-950/60 text-yellow-300 border-yellow-700/40",
  "rules_fallback_after_llm_failure":   "bg-red-950/60 text-red-300 border-red-700/40",
  "rules_fallback_low_confidence":      "bg-orange-950/60 text-orange-300 border-orange-700/40",
};

function ClassifiedByBadge({ value }) {
  const style = CLASSIFIED_BY_STYLES[value] || "bg-gray-800/80 text-gray-400 border-gray-700/40";
  return (
    <span className={`text-[10px] border rounded px-1.5 py-0.5 font-mono ${style}`}>
      {value}
    </span>
  );
}

function DebugRow({ item }) {
  const [expanded, setExpanded] = useState(false);
  const decision = item.score?.decision || "hidden";
  const reasoning = item.score?.reasoning || [];
  const isCluster = item.type === "cluster";

  const title = isCluster ? item.clusterTitle : item.title;
  const source = isCluster
    ? (item.sourceDisplayNames || item.sources || []).join(", ")
    : item.sourceDisplayName;
  const publishedAt = item.publishedAt || item.firstSeenAt;

  return (
    <div className={`border rounded-lg overflow-hidden transition-all ${
      decision === "hidden"
        ? "border-red-900/40 bg-red-950/10"
        : decision === "push"
        ? "border-amber-700/40 bg-amber-950/10"
        : "border-gray-800 bg-gray-900/50"
    }`}>
      {/* Row header */}
      <button
        className="w-full text-right p-3 flex items-start justify-between gap-3 hover:bg-white/2 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <DecisionBadge decision={decision} size="xs" />
            {isCluster && (
              <span className="text-[10px] bg-gray-700/60 text-gray-400 rounded px-1.5 py-0.5 border border-gray-600/40">קלאסטר</span>
            )}
          </div>
          <p className="text-sm text-gray-200 font-medium leading-snug truncate">{title}</p>
          {item.subtitle && (
            <p className="text-xs text-gray-500 mt-0.5 line-clamp-3 leading-snug">
              {item.subtitle}
            </p>
          )}
          <p className="text-xs text-gray-600 mt-0.5">{source} · {item.sport} · {item.league || "—"}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {expanded ? <ChevronUp size={14} className="text-gray-600" /> : <ChevronDown size={14} className="text-gray-600" />}
        </div>
      </button>

      {/* Expanded debug info */}
      {expanded && (
        <div className="border-t border-gray-800/60 p-3 space-y-3">
          {/* Metadata grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {[
              { label: "ספורט", value: item.sport || "—" },
              { label: "ליגה", value: item.league || "—" },
              { label: "סוג אירוע", value: item.eventType || "—" },
              { label: "חשיבות", value: item.importance || "—" },
              { label: "ביטחון", value: item.confidence ? `${Math.round(item.confidence * 100)}%` : "—" },
              { label: "ישויות", value: (item.entities || []).join(", ") || "—" },
              { label: "נושא תואם", value: item.score?.matchedTopic || "—" },
              { label: "כלל תואם", value: item.score?.matchedRule || "—" }
            ].map(({ label, value }) => (
              <div key={label} className="bg-gray-800/60 rounded p-2">
                <div className="text-gray-600 mb-0.5">{label}</div>
                <div className="text-gray-300 font-medium truncate" title={value}>{value}</div>
              </div>
            ))}
          </div>

          {/* LLM Classification metadata */}
          {item.classifiedBy && (
            <div className="space-y-1.5">
              <p className="text-[10px] text-gray-600 font-medium uppercase tracking-wide">סיווג LLM</p>
              <div className="flex items-center gap-2 flex-wrap">
                <ClassifiedByBadge value={item.classifiedBy} />
                {item.classificationProvider && item.classificationProvider !== "rules" && (
                  <span className="text-[10px] text-gray-500 bg-gray-800/60 border border-gray-700/40 rounded px-1.5 py-0.5">
                    {item.classificationProvider}
                  </span>
                )}
                {item.classificationConfidence != null && (
                  <span className="text-[10px] text-gray-500">
                    ביטחון LLM: {Math.round(item.classificationConfidence * 100)}%
                  </span>
                )}
              </div>
              {item.classificationReason && (
                <p className="text-[11px] text-gray-500 italic leading-snug">
                  {item.classificationReason}
                </p>
              )}
            </div>
          )}

          {/* Reasoning chain */}
          <div>
            <p className="text-xs text-gray-600 font-medium mb-2 flex items-center gap-1">
              <Bug size={11} />
              שרשרת ההחלטה:
            </p>
            <div className="space-y-1">
              {reasoning.map((line, i) => {
                const isDecision = line.includes("החלטה סופית");
                const isHidden = line.includes("מוסתר") || line.includes("hidden");
                const isPositive = line.includes("push") || line.includes("דורש תשומת לב") || line.includes("חשוב");
                return (
                  <div
                    key={i}
                    className={`text-xs px-2 py-1 rounded border-r-2 ${
                      isDecision
                        ? isHidden
                          ? "text-red-300 bg-red-950/30 border-red-600"
                          : isPositive
                          ? "text-amber-300 bg-amber-950/30 border-amber-600"
                          : "text-emerald-300 bg-emerald-950/20 border-emerald-600"
                        : "text-gray-400 bg-gray-800/30 border-gray-700"
                    }`}
                  >
                    {i + 1}. {line}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Comparison Row ────────────────────────────────────────────
function ComparisonRow({ item, profiles }) {
  const [expanded, setExpanded] = useState(false);
  const title = item.type === "cluster" ? item.clusterTitle : item.title;
  const profileIds = Object.keys(item.profileScores || {});

  // Check if profiles disagree (different decisions)
  const decisions = profileIds.map(pid => item.profileScores[pid]?.decision);
  const disagreement = new Set(decisions).size > 1;

  return (
    <div className={`border rounded-lg overflow-hidden ${
      disagreement ? "border-purple-700/40 bg-purple-950/10" : "border-gray-800 bg-gray-900/50"
    }`}>
      <button
        className="w-full text-right p-3 flex items-start justify-between gap-3 hover:bg-white/2 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex-1 min-w-0">
          {disagreement && (
            <span className="text-[10px] text-purple-400 bg-purple-500/10 border border-purple-500/20 rounded px-1.5 py-0.5 mb-1 inline-block">
              חוסר הסכמה
            </span>
          )}
          <p className="text-sm text-gray-200 font-medium leading-snug truncate">{title}</p>
          <p className="text-xs text-gray-600 mt-0.5">{item.sport} · {item.league || "—"} · {item.eventType || "—"}</p>
        </div>
        {/* Profile decision badges */}
        <div className="flex flex-col gap-1 flex-shrink-0 items-end">
          {profileIds.map(pid => (
            <div key={pid} className="flex items-center gap-1.5">
              <span className="text-[10px] text-gray-600 truncate max-w-[80px]">{profiles[pid]?.displayName}</span>
              <DecisionBadge decision={item.profileScores[pid]?.decision} size="xs" />
            </div>
          ))}
        </div>
        <div className="flex-shrink-0 mt-1">
          {expanded ? <ChevronUp size={13} className="text-gray-600" /> : <ChevronDown size={13} className="text-gray-600" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-800/60 p-3 grid gap-3" style={{ gridTemplateColumns: `repeat(${profileIds.length}, 1fr)` }}>
          {profileIds.map(pid => {
            const score = item.profileScores[pid];
            const reasoning = score?.reasoning || [];
            return (
              <div key={pid} className="space-y-1">
                <div className="flex items-center gap-1.5 mb-2">
                  <DecisionBadge decision={score?.decision} size="xs" />
                  <span className="text-xs text-gray-400">{profiles[pid]?.displayName}</span>
                </div>
                <div className="space-y-0.5">
                  {reasoning.map((line, i) => {
                    const isFinal = line.includes("החלטה סופית");
                    return (
                      <p key={i} className={`text-xs leading-relaxed ${
                        isFinal ? "text-gray-200 font-medium" : "text-gray-500"
                      }`}>
                        {i + 1}. {line}
                      </p>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function Debug() {
  const { debugItems, activeProfile, comparisonItems, profiles } = useApp();
  const [filterDecision, setFilterDecision] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState("debug");

  const filtered = useMemo(() => {
    return debugItems.filter(item => {
      if (filterDecision !== "all" && item.score?.decision !== filterDecision) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const title = (item.type === "cluster" ? item.clusterTitle : item.title) || "";
        return title.toLowerCase().includes(q) ||
          (item.sport || "").includes(q) ||
          (item.league || "").toLowerCase().includes(q);
      }
      return true;
    });
  }, [debugItems, filterDecision, searchQuery]);

  const hiddenCount = debugItems.filter(i => i.score?.decision === "hidden").length;
  const visibleCount = debugItems.length - hiddenCount;

  const decisionCounts = useMemo(() => {
    const counts = { hidden: 0, low_feed: 0, feed: 0, high_feed: 0, push: 0 };
    debugItems.forEach(item => {
      const d = item.score?.decision || "hidden";
      if (counts[d] !== undefined) counts[d]++;
    });
    return counts;
  }, [debugItems]);

  return (
    <div className="space-y-4 pb-20 md:pb-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Bug size={18} className="text-amber-400" />
            פאנל דיבאג
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            פרופיל פעיל: <span className="text-emerald-400">{activeProfile?.displayName}</span>
            {" · "}
            {visibleCount} מוצגים, {hiddenCount} מוסתרים
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        <button
          onClick={() => setActiveTab("debug")}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
            activeTab === "debug" ? "text-amber-400 border-amber-400" : "text-gray-500 border-transparent hover:text-gray-300"
          }`}
        >
          <Bug size={13} />
          פאנל דיבאג
        </button>
        <button
          onClick={() => setActiveTab("compare")}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
            activeTab === "compare" ? "text-purple-400 border-purple-400" : "text-gray-500 border-transparent hover:text-gray-300"
          }`}
        >
          <GitCompare size={13} />
          השוואת פרופילים
        </button>
      </div>

      {/* ── Comparison Tab ─────────────────────────────────────── */}
      {activeTab === "compare" && (
        <div className="space-y-3">
          <div className="bg-purple-950/20 border border-purple-900/40 rounded-lg p-3">
            <p className="text-xs text-purple-300/80">
              השוואה בין כל הפרופילים לכל כתבה. שורות <span className="text-purple-300 font-medium">סגולות</span> = פרופילים מחליטים שונה.
            </p>
          </div>
          {comparisonItems.map(item => (
            <ComparisonRow key={item.id} item={item} profiles={profiles} />
          ))}
        </div>
      )}

      {/* ── Debug Tab ──────────────────────────────────────────── */}
      {activeTab === "debug" && (
        <>
          {/* Stats Row */}
          <div className="grid grid-cols-5 gap-1.5">
            {[
              { key: "push", label: "דורש תשומת לב", color: "text-amber-400 border-amber-900/40" },
              { key: "high_feed", label: "חשוב", color: "text-emerald-400 border-emerald-900/40" },
              { key: "feed", label: "רגיל", color: "text-blue-400 border-blue-900/40" },
              { key: "low_feed", label: "נמוך", color: "text-gray-400 border-gray-800" },
              { key: "hidden", label: "מוסתר", color: "text-red-400 border-red-900/40" }
            ].map(({ key, label, color }) => (
              <div key={key} className={`text-center bg-gray-900 rounded-lg p-2 border ${color.split(" ").slice(-1)[0]}`}>
                <div className={`text-xl font-bold ${color.split(" ")[0]}`}>{decisionCounts[key]}</div>
                <div className="text-[9px] text-gray-600 leading-tight mt-0.5">{label}</div>
              </div>
            ))}
          </div>

          {/* Filters */}
          <div className="flex gap-2 flex-wrap">
            <div className="relative flex-1 min-w-[180px]">
              <Search size={13} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600" />
              <input
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="חיפוש לפי כותרת..."
                className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-3 pr-8 py-2 text-xs text-gray-300 placeholder-gray-600 focus:outline-none focus:border-gray-600"
              />
            </div>
            {["all", "push", "high_feed", "feed", "low_feed", "hidden"].map(d => (
              <button
                key={d}
                onClick={() => setFilterDecision(d)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                  filterDecision === d
                    ? "bg-gray-700 border-gray-500 text-white"
                    : "bg-gray-900 border-gray-800 text-gray-500 hover:border-gray-700"
                }`}
              >
                {d === "all" ? "הכל" : d === "push" ? "Push" : d === "high_feed" ? "High" : d === "feed" ? "Feed" : d === "low_feed" ? "Low" : "Hidden"}
                {d !== "all" && <span className="mr-1 text-gray-600">({decisionCounts[d] || 0})</span>}
              </button>
            ))}
          </div>

          <div className="bg-amber-950/20 border border-amber-900/40 rounded-lg p-3">
            <p className="text-xs text-amber-400/80">
              <span className="font-medium">מצב דיבאג:</span> כל הפריטים גלויים, כולל מוסתרים. לחץ על שורה לשרשרת ההחלטה המלאה.
            </p>
          </div>

          <div className="space-y-2">
            {filtered.length === 0 ? (
              <div className="text-center py-8 text-gray-600 text-sm">לא נמצאו פריטים</div>
            ) : (
              filtered.map(item => <DebugRow key={item.id} item={item} />)
            )}
          </div>
        </>
      )}
    </div>
  );
}