import React, { useState, useEffect, useCallback } from "react";
import { RefreshCw, Play, CheckCircle2, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";
import { getIngestSources, runIngestion, getIngestRuns, getIngestQuality } from "@/api/client";
import { normalizeIngestResultFromApi, formatMs, formatDuration } from "@/api/normalizers";
import { cn } from "@/lib/utils";
import SectionCard from "@/components/shared/SectionCard";
import PulseDot from "@/components/shared/PulseDot";
import MonoValue from "@/components/shared/MonoValue";
import { consoleButton, consoleAlert } from "@/components/ops/consoleStyles";

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
    <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs mt-2 pt-1.5 border-t border-border/60">
      <span className="text-text-dim font-medium">ביצועים:</span>
      {result.fetchMs != null && (
        <span className="text-text-dim">שליפה <MonoValue className="text-text-secondary">{formatMs(result.fetchMs)}</MonoValue></span>
      )}
      {result.totalMs != null && (
        <span className="text-text-dim">סה״כ <MonoValue className="text-text-secondary">{formatDuration(result.totalMs)}</MonoValue></span>
      )}
      {llmActive ? (
        <>
          <span className="text-text-dim">
            LLM <MonoValue className="text-text-secondary">{result.llmSuccesses}/{result.llmAttempts}</MonoValue>
          </span>
          {(result.llmSkipped ?? 0) > 0 && (
            <span className="text-text-dim">דולגו <MonoValue className="text-text-secondary">{result.llmSkipped}</MonoValue></span>
          )}
          {result.llmAvgMs != null && (
            <span className="text-text-dim">ממוצע <MonoValue className="text-text-secondary">{formatMs(result.llmAvgMs)}</MonoValue></span>
          )}
          {result.llmP95Ms != null && (
            <span className="text-text-dim">P95 <MonoValue className="text-text-secondary">{formatMs(result.llmP95Ms)}</MonoValue></span>
          )}
          {totalFallbacks === 0 ? (
            <span className="text-text-dim">נפילות <MonoValue className="text-text-secondary">0</MonoValue></span>
          ) : (
            <span className="text-signal-push/90">
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
        <span className="text-text-dim">LLM לא הופעל</span>
      )}
    </div>
  );
}

function SourceResultCard({ result }) {
  const hasNew = result.inserted > 0;
  return (
    <div className={cn(
      "rounded-[10px] border p-3",
      hasNew ? "border-signal-high/30 bg-signal-high/5" : "border-border bg-surface-2"
    )}>
      <div className="text-xs font-medium text-foreground mb-2">{result.sourceId}</div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {RESULT_LABELS.map(({ key, label }) => (
          <span key={key} className="flex gap-1">
            <span className="text-text-dim">{label}:</span>
            <MonoValue className={
              key === "inserted" && result[key] > 0
                ? "text-signal-high font-medium"
                : key === "failed" && result[key] > 0
                  ? "text-signal-hidden font-medium"
                  : "text-text-secondary"
            }>
              {result[key] ?? 0}
            </MonoValue>
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
        <span className="text-text-dim">
          סה״כ כתבות RSS: <MonoValue className="text-text-secondary">{quality.total_rss_articles}</MonoValue>
        </span>
        <span className="text-text-dim">
          ביטחון נמוך:{" "}
          <MonoValue className={quality.low_confidence_count > 0 ? "text-signal-push" : "text-text-secondary"}>
            {quality.low_confidence_count}
          </MonoValue>
        </span>
        <span className="text-text-dim">
          לבדיקה: <MonoValue className="text-text-secondary">{quality.questionable_articles?.length ?? 0}</MonoValue>
        </span>
      </div>

      <div>
        <div className="text-text-dim mb-1">ספורט</div>
        <div className="flex gap-2 flex-wrap">
          {Object.entries(quality.sport_breakdown).map(([sport, count]) => (
            <span key={sport} className="px-2 py-0.5 rounded-full border border-border bg-surface-2 text-text-secondary">
              {sport}: {count}
            </span>
          ))}
        </div>
      </div>

      {Object.keys(quality.event_type_breakdown).length > 0 && (
        <div>
          <div className="text-text-dim mb-1">סוגי אירועים</div>
          <div className="flex gap-2 flex-wrap">
            {Object.entries(quality.event_type_breakdown)
              .sort(([, a], [, b]) => b - a)
              .slice(0, 8)
              .map(([ev, count]) => (
                <span key={ev} className="px-2 py-0.5 rounded-full border border-border bg-surface-2 text-text-secondary">
                  {ev}: {count}
                </span>
              ))}
          </div>
        </div>
      )}

      {quality.questionable_articles?.length > 0 && (
        <div>
          <div className="text-text-dim mb-1">
            כתבות לבדיקה — {quality.questionable_articles.length} כתבות
          </div>
          <div className="space-y-1">
            {quality.questionable_articles.slice(0, 5).map((a) => (
              <div key={a.id} className="bg-surface-2 border border-border rounded-[10px] px-3 py-2">
                <div className="text-text-secondary mb-0.5 truncate">{a.title}</div>
                <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-text-dim">
                  <span>{a.source}</span>
                  <span>·</span>
                  <span>{a.sport}</span>
                  {a.league && (<><span>·</span><span>{a.league}</span></>)}
                  <span>·</span>
                  <span className="text-signal-push/80">{a.reasons.join(", ")}</span>
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
      <SectionCard title="ייבוא כתבות RSS" icon={RefreshCw}>
        <p className="text-xs text-text-secondary">ייבוא RSS זמין רק במצב שרת.</p>
        <p className="text-xs text-text-dim mt-1">
          מצב מקומי פעיל — כדי לראות RSS אמיתי הפעל <span className="font-mono">VITE_DATA_MODE=backend</span>.
        </p>
      </SectionCard>
    );
  }

  const totalInserted = lastResult?.sources?.reduce((sum, s) => sum + (s.inserted ?? 0), 0) ?? 0;

  const sourcePill = (active) => cn(
    "text-xs px-3 py-1.5 rounded-full border transition-colors",
    active
      ? "border-signal-feed/40 bg-signal-feed/15 text-signal-feed"
      : "border-border text-text-dim hover:border-text-dim hover:text-text-secondary"
  );

  return (
    <SectionCard title="ייבוא כתבות RSS" icon={RefreshCw}>
      <div className="space-y-4">
        {error && (
          <div className={consoleAlert("error")}>
            <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Source selector */}
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => setSelectedSource("all")} className={sourcePill(selectedSource === "all")}>
            כל המקורות
          </button>
          {ingestSources.map((src) => (
            <button
              key={src.source_id}
              onClick={() => setSelectedSource(src.source_id)}
              className={sourcePill(selectedSource === src.source_id)}
            >
              {src.display_name}
            </button>
          ))}
        </div>

        <button onClick={handleRun} disabled={isRunning} className={consoleButton("primary")}>
          {isRunning ? (
            <><RefreshCw size={14} className="animate-spin" /> מייבא...</>
          ) : (
            <><Play size={14} /> הרץ ייבוא עכשיו</>
          )}
        </button>

        {/* Result summary */}
        {lastResult && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-text-secondary">
              <CheckCircle2 size={12} className="text-signal-high flex-shrink-0" />
              {totalInserted > 0
                ? `הייבוא הסתיים — נוספו ${totalInserted} כתבות חדשות`
                : "הייבוא הסתיים — לא נוספו כתבות חדשות"}
            </div>
            {lastResult.sources?.map((src) => (
              <SourceResultCard key={src.source_id} result={src} />
            ))}
          </div>
        )}

        {/* Recent runs */}
        {recentRuns.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs text-text-dim font-medium">ריצות אחרונות</div>
            {recentRuns.map((run) => (
              <div
                key={run.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs bg-surface-2 border border-border rounded-[10px] px-3 py-2"
              >
                <PulseDot tone={run.status === "ok" ? "high" : "hidden"} />
                <span className="text-text-secondary font-medium">{run.source_id}</span>
                <span className="text-text-dim">{formatRunTime(run.started_at)}</span>
                <span className="text-text-dim">
                  נמצאו: {run.fetched_count} | נוספו: {run.inserted_count} | כפולים: {run.skipped_duplicate_count}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Quality panel toggle */}
        <div className="border-t border-border/60 pt-3">
          <button
            onClick={handleToggleQuality}
            disabled={isLoadingQuality}
            className="flex items-center gap-1.5 text-xs text-text-dim hover:text-text-secondary disabled:cursor-not-allowed transition-colors"
          >
            {isLoadingQuality
              ? <RefreshCw size={11} className="animate-spin" />
              : showQuality ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            איכות הסיווג
          </button>
          {showQuality && quality && <QualityPanel quality={quality} />}
        </div>
      </div>
    </SectionCard>
  );
}
