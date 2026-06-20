import React, { useState, useEffect, useCallback } from "react";
import { RefreshCw, Play, CheckCircle2, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";
import { getIngestSources, runIngestion, getIngestRuns, getIngestQuality } from "@/api/client";
import { normalizeIngestResultFromApi, formatMs, formatDuration } from "@/api/normalizers";

const RESULT_LABELS = [
  { key: "fetched",          label: "נמצאו" },
  { key: "inserted",         label: "נוספו" },
  { key: "skippedDuplicate", label: "דולגו ככפולים" },
  { key: "skippedFiltered",  label: "סוננו" },
  { key: "failed",           label: "נכשלו" },
];

function formatRunTime(isoStr) {
  if (!isoStr) return "—";
  try {
    return new Date(isoStr).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}

function SourceTimingRow({ result }) {
  const hasTiming = result.fetchMs != null || result.totalMs != null;
  if (!hasTiming) return null;

  const llmActive = result.llmAttempts > 0;
  const totalFallbacks =
    (result.llmFallbackConnectError ?? 0) +
    (result.llmFallbackTimeoutOrParse ?? 0) +
    (result.llmFallbackLowConfidence ?? 0);

  return (
    <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs mt-2 pt-1.5 border-t border-gray-800/50">
      <span className="text-gray-600 font-medium">ביצועים:</span>
      {result.fetchMs != null && (
        <span className="text-gray-600">
          שליפה <span className="text-gray-400">{formatMs(result.fetchMs)}</span>
        </span>
      )}
      {result.totalMs != null && (
        <span className="text-gray-600">
          סה״כ <span className="text-gray-400">{formatDuration(result.totalMs)}</span>
        </span>
      )}
      {llmActive ? (
        <>
          <span className="text-gray-600">
            LLM{" "}
            <span className="text-gray-400">
              {result.llmSuccesses}/{result.llmAttempts}
            </span>
          </span>
          {result.llmAvgMs != null && (
            <span className="text-gray-600">
              ממוצע <span className="text-gray-400">{formatMs(result.llmAvgMs)}</span>
            </span>
          )}
          {result.llmP95Ms != null && (
            <span className="text-gray-600">
              P95 <span className="text-gray-400">{formatMs(result.llmP95Ms)}</span>
            </span>
          )}
          {totalFallbacks === 0 ? (
            <span className="text-gray-600">
              נפילות <span className="text-gray-400">0</span>
            </span>
          ) : (
            <span className="text-amber-500/80">
              נפילות:{" "}
              {result.llmFallbackConnectError > 0 && `חיבור ${result.llmFallbackConnectError}`}
              {result.llmFallbackConnectError > 0 && result.llmFallbackTimeoutOrParse > 0 && " · "}
              {result.llmFallbackTimeoutOrParse > 0 && `timeout/parse ${result.llmFallbackTimeoutOrParse}`}
              {(result.llmFallbackConnectError > 0 || result.llmFallbackTimeoutOrParse > 0) && result.llmFallbackLowConfidence > 0 && " · "}
              {result.llmFallbackLowConfidence > 0 && `confidence ${result.llmFallbackLowConfidence}`}
            </span>
          )}
        </>
      ) : (
        <span className="text-gray-600">LLM לא הופעל</span>
      )}
    </div>
  );
}

function SourceResultCard({ result }) {
  const hasNew = result.inserted > 0;
  return (
    <div className={`rounded-lg border p-3 ${
      hasNew
        ? "border-emerald-800/40 bg-emerald-900/10"
        : "border-gray-800 bg-gray-900/30"
    }`}>
      <div className="text-xs font-medium text-gray-300 mb-2">{result.sourceId}</div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {RESULT_LABELS.map(({ key, label }) => (
          <span key={key} className="flex gap-1">
            <span className="text-gray-600">{label}:</span>
            <span className={
              key === "inserted" && result[key] > 0
                ? "text-emerald-400 font-medium"
                : key === "failed" && result[key] > 0
                  ? "text-red-400 font-medium"
                  : "text-gray-300"
            }>
              {result[key] ?? 0}
            </span>
          </span>
        ))}
      </div>
      <SourceTimingRow result={result} />
    </div>
  );
}

function QualityPanel({ quality }) {
  return (
    <div className="mt-3 space-y-3 text-xs">
      <div className="flex gap-4 flex-wrap">
        <span className="text-gray-500">
          סה״כ כתבות RSS:{" "}
          <span className="text-gray-300">{quality.total_rss_articles}</span>
        </span>
        <span className="text-gray-500">
          ביטחון נמוך:{" "}
          <span className={quality.low_confidence_count > 0 ? "text-amber-400" : "text-gray-300"}>
            {quality.low_confidence_count}
          </span>
        </span>
        <span className="text-gray-500">
          לבדיקה:{" "}
          <span className="text-gray-300">{quality.questionable_articles?.length ?? 0}</span>
        </span>
      </div>

      <div>
        <div className="text-gray-600 mb-1">ספורט</div>
        <div className="flex gap-2 flex-wrap">
          {Object.entries(quality.sport_breakdown).map(([sport, count]) => (
            <span
              key={sport}
              className="px-2 py-0.5 rounded border border-gray-800 bg-gray-900/30 text-gray-400"
            >
              {sport}: {count}
            </span>
          ))}
        </div>
      </div>

      {Object.keys(quality.event_type_breakdown).length > 0 && (
        <div>
          <div className="text-gray-600 mb-1">סוגי אירועים</div>
          <div className="flex gap-2 flex-wrap">
            {Object.entries(quality.event_type_breakdown)
              .sort(([, a], [, b]) => b - a)
              .slice(0, 8)
              .map(([ev, count]) => (
                <span
                  key={ev}
                  className="px-2 py-0.5 rounded border border-gray-800 bg-gray-900/30 text-gray-400"
                >
                  {ev}: {count}
                </span>
              ))}
          </div>
        </div>
      )}

      {quality.questionable_articles?.length > 0 && (
        <div>
          <div className="text-gray-600 mb-1">
            כתבות לבדיקה — {quality.questionable_articles.length} כתבות
          </div>
          <div className="space-y-1">
            {quality.questionable_articles.slice(0, 5).map(a => (
              <div
                key={a.id}
                className="bg-gray-900/30 border border-gray-800 rounded-lg px-3 py-2"
              >
                <div className="text-gray-400 mb-0.5 truncate">{a.title}</div>
                <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-gray-600">
                  <span>{a.source}</span>
                  <span>·</span>
                  <span>{a.sport}</span>
                  {a.league && (
                    <>
                      <span>·</span>
                      <span>{a.league}</span>
                    </>
                  )}
                  <span>·</span>
                  <span className="text-amber-600/80">{a.reasons.join(", ")}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function IngestionPanel({ isBackendMode, onFeedRefresh }) {
  const [ingestSources, setIngestSources] = useState([]);
  const [selectedSource, setSelectedSource] = useState("all");
  const [isRunning, setIsRunning] = useState(false);
  const [lastResult, setLastResult] = useState(null);
  const [recentRuns, setRecentRuns] = useState([]);
  const [quality, setQuality] = useState(null);
  const [isLoadingQuality, setIsLoadingQuality] = useState(false);
  const [showQuality, setShowQuality] = useState(false);
  const [error, setError] = useState(null);

  const loadMeta = useCallback(async () => {
    if (!isBackendMode) return;
    try {
      const [sources, runs] = await Promise.all([
        getIngestSources(),
        getIngestRuns(5),
      ]);
      setIngestSources(sources);
      setRecentRuns(runs);
    } catch (err) {
      setError(err.message);
    }
  }, [isBackendMode]);

  useEffect(() => {
    loadMeta();
  }, [loadMeta]);

  const handleRun = async () => {
    setIsRunning(true);
    setError(null);
    try {
      const sourceId = selectedSource === "all" ? undefined : selectedSource;
      const raw = await runIngestion(sourceId);
      const result = {
        ...raw,
        sources: (raw.sources ?? []).map(normalizeIngestResultFromApi),
      };
      setLastResult(result);
      const runs = await getIngestRuns(5);
      setRecentRuns(runs);
      if (onFeedRefresh) onFeedRefresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsRunning(false);
    }
  };

  const handleToggleQuality = async () => {
    if (showQuality) {
      setShowQuality(false);
      return;
    }
    setIsLoadingQuality(true);
    try {
      const q = await getIngestQuality();
      setQuality(q);
      setShowQuality(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoadingQuality(false);
    }
  };

  if (!isBackendMode) {
    return (
      <div className="border border-gray-800 rounded-xl p-4 bg-gray-900/20">
        <h2 className="text-sm font-semibold text-gray-500 mb-1">ייבוא כתבות RSS</h2>
        <p className="text-xs text-gray-600">ייבוא RSS זמין רק במצב שרת</p>
        <p className="text-xs text-gray-700 mt-1">
          מצב מקומי פעיל — כדי לראות RSS אמיתי הפעל VITE_DATA_MODE=backend
        </p>
      </div>
    );
  }

  const totalInserted = lastResult?.sources?.reduce((sum, s) => sum + (s.inserted ?? 0), 0) ?? 0;

  return (
    <div className="border border-gray-700 rounded-xl bg-gray-900/40 p-4 space-y-4">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2">
        <RefreshCw size={14} className="text-blue-400" />
        ייבוא כתבות RSS
      </h2>

      {error && (
        <div className="flex items-start gap-2 text-xs text-red-400 bg-red-900/10 border border-red-800/30 rounded-lg px-3 py-2">
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Source selector */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setSelectedSource("all")}
          className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${
            selectedSource === "all"
              ? "border-blue-500/50 bg-blue-500/10 text-blue-300"
              : "border-gray-700 text-gray-500 hover:border-gray-600 hover:text-gray-400"
          }`}
        >
          כל המקורות
        </button>
        {ingestSources.map(src => (
          <button
            key={src.source_id}
            onClick={() => setSelectedSource(src.source_id)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${
              selectedSource === src.source_id
                ? "border-blue-500/50 bg-blue-500/10 text-blue-300"
                : "border-gray-700 text-gray-500 hover:border-gray-600 hover:text-gray-400"
            }`}
          >
            {src.display_name}
          </button>
        ))}
      </div>

      {/* Run button */}
      <button
        onClick={handleRun}
        disabled={isRunning}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-blue-900/40 disabled:cursor-not-allowed text-white disabled:text-blue-400 text-sm font-medium transition-all"
      >
        {isRunning ? (
          <>
            <RefreshCw size={14} className="animate-spin" />
            מייבא...
          </>
        ) : (
          <>
            <Play size={14} />
            הרץ ייבוא עכשיו
          </>
        )}
      </button>

      {/* Result summary */}
      {lastResult && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <CheckCircle2 size={12} className="text-emerald-400 flex-shrink-0" />
            {totalInserted > 0
              ? `הייבוא הסתיים — נוספו ${totalInserted} כתבות חדשות`
              : "הייבוא הסתיים — לא נוספו כתבות חדשות"}
          </div>
          {lastResult.sources?.map(src => (
            <SourceResultCard key={src.source_id} result={src} />
          ))}
        </div>
      )}

      {/* Recent runs */}
      {recentRuns.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs text-gray-600 font-medium">ריצות אחרונות</div>
          {recentRuns.map(run => (
            <div
              key={run.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs bg-gray-900/30 border border-gray-800 rounded-lg px-3 py-2"
            >
              <span className={run.status === "ok" ? "text-emerald-500" : "text-red-400"}>●</span>
              <span className="text-gray-400 font-medium">{run.source_id}</span>
              <span className="text-gray-700">{formatRunTime(run.started_at)}</span>
              <span className="text-gray-600">
                נמצאו: {run.fetched_count} | נוספו: {run.inserted_count} | כפולים: {run.skipped_duplicate_count}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Quality panel toggle */}
      <div className="border-t border-gray-800/60 pt-3">
        <button
          onClick={handleToggleQuality}
          disabled={isLoadingQuality}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          {isLoadingQuality
            ? <RefreshCw size={11} className="animate-spin" />
            : showQuality
              ? <ChevronUp size={11} />
              : <ChevronDown size={11} />
          }
          איכות הסיווג
        </button>

        {showQuality && quality && <QualityPanel quality={quality} />}
      </div>

    </div>
  );
}
