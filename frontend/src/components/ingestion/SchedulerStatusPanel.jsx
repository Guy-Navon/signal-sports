import React, { useState, useEffect, useCallback } from "react";
import { Clock, Play, RefreshCw, AlertCircle } from "lucide-react";
import {
  getSchedulerStatus,
  getSourceHealth,
  runSchedulerNow,
  isIngestionBusyError,
} from "@/api/client";
import {
  normalizeSchedulerStatusFromApi,
  normalizeSourceHealthFromApi,
  freshnessBadge,
  sourceTypeLabel,
} from "@/api/normalizers";

function formatDateTime(isoStr) {
  if (!isoStr) return "—";
  try {
    return new Date(isoStr).toLocaleString("he-IL", {
      day: "2-digit", month: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

const LAST_STATUS_LABELS = {
  ok: { label: "הצליח", className: "text-emerald-400" },
  error: { label: "שגיאה", className: "text-red-400" },
  skipped: { label: "דולג (ריצה פעילה)", className: "text-amber-400" },
  never_run: { label: "טרם רץ", className: "text-gray-500" },
};

function SourceHealthCard({ health }) {
  const badge = freshnessBadge(health.freshness);
  const hasCounts = health.lastFetchedCount != null;

  return (
    <div className={`rounded-lg border p-3 ${
      health.enabled ? "border-gray-800 bg-gray-900/30" : "border-gray-800/60 bg-gray-900/20 opacity-70"
    }`}>
      <div className="flex items-center gap-2 flex-wrap mb-1.5">
        <span className="text-xs font-medium text-gray-300">{health.displayName}</span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${badge.colorClass}`}>
          {badge.label}
        </span>
        <span className="text-[10px] px-1.5 py-0.5 rounded border border-gray-700/60 bg-gray-800/40 text-gray-400">
          {sourceTypeLabel(health.sourceType)}
        </span>
        {health.isPilot && (
          <span className="text-[10px] px-1.5 py-0.5 rounded border border-purple-500/40 bg-purple-500/10 text-purple-300">
            פיילוט
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-gray-600">
        <span>
          ריצה אחרונה: <span className="text-gray-400">{formatDateTime(health.lastRunAt)}</span>
        </span>
        {hasCounts && (
          <span>
            נמצאו {health.lastFetchedCount} · נוספו{" "}
            <span className={health.lastInsertedCount > 0 ? "text-emerald-400" : "text-gray-400"}>
              {health.lastInsertedCount}
            </span>
            {" "}· נכשלו{" "}
            <span className={health.lastFailedCount > 0 ? "text-red-400" : "text-gray-400"}>
              {health.lastFailedCount}
            </span>
          </span>
        )}
        {health.consecutiveFailures > 0 && (
          <span className="text-red-400">
            {health.consecutiveFailures} כשלונות רצופים
          </span>
        )}
      </div>
      {health.lastErrorMessage && (
        <div className="mt-1 text-xs text-red-400/80 truncate">
          {health.lastErrorMessage}
        </div>
      )}
    </div>
  );
}

export default function SchedulerStatusPanel({ isBackendMode, onFeedRefresh }) {
  const [status, setStatus] = useState(null);
  const [health, setHealth] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState(null);

  const loadStatus = useCallback(async () => {
    if (!isBackendMode) return;
    try {
      const [rawStatus, rawHealth] = await Promise.all([
        getSchedulerStatus(),
        getSourceHealth(),
      ]);
      setStatus(normalizeSchedulerStatusFromApi(rawStatus));
      setHealth(rawHealth.map(normalizeSourceHealthFromApi));
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, [isBackendMode]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleRunNow = async () => {
    setIsRunning(true);
    setError(null);
    try {
      await runSchedulerNow();
      if (onFeedRefresh) onFeedRefresh();
    } catch (err) {
      if (isIngestionBusyError(err)) {
        setError("ייבוא פעיל כרגע — נסה שוב בעוד רגע");
      } else {
        setError(err.message);
      }
    } finally {
      setIsRunning(false);
      loadStatus();
    }
  };

  // Local mode: scheduler status is a backend-only feature — hide entirely
  // (IngestionPanel already shows the "backend mode required" explanation).
  if (!isBackendMode) return null;

  const runActive = isRunning || status?.activeRun != null;
  const lastStatusInfo = LAST_STATUS_LABELS[status?.lastStatus] ?? LAST_STATUS_LABELS.never_run;

  return (
    <div className="border border-gray-700 rounded-xl bg-gray-900/40 p-4 space-y-4">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2">
        <Clock size={14} className="text-blue-400" />
        סטטוס ייבוא אוטומטי
      </h2>

      {error && (
        <div className="flex items-start gap-2 text-xs text-amber-400 bg-amber-900/10 border border-amber-800/30 rounded-lg px-3 py-2">
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {status && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          <span className="text-gray-600">
            תזמון:{" "}
            <span className={status.enabled ? "text-emerald-400" : "text-gray-400"}>
              {status.enabled ? `פעיל — כל ${status.intervalMinutes} דקות` : "כבוי"}
            </span>
          </span>
          {status.enabled && status.nextRunAt && (
            <span className="text-gray-600">
              ריצה הבאה: <span className="text-gray-400">{formatDateTime(status.nextRunAt)}</span>
            </span>
          )}
          <span className="text-gray-600">
            ריצה אחרונה:{" "}
            <span className="text-gray-400">{formatDateTime(status.lastStartedAt)}</span>
            {" "}
            <span className={lastStatusInfo.className}>({lastStatusInfo.label})</span>
          </span>
          {status.lastError && (
            <span className="text-red-400/80 truncate max-w-full">
              שגיאה אחרונה: {status.lastError}
            </span>
          )}
        </div>
      )}

      <button
        onClick={handleRunNow}
        disabled={runActive}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-blue-900/40 disabled:cursor-not-allowed text-white disabled:text-blue-400 text-sm font-medium transition-all"
      >
        {runActive ? (
          <>
            <RefreshCw size={14} className="animate-spin" />
            ייבוא פעיל כרגע
          </>
        ) : (
          <>
            <Play size={14} />
            הרץ עכשיו
          </>
        )}
      </button>

      {health.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs text-gray-600 font-medium">בריאות מקורות</div>
          {health.map(h => (
            <SourceHealthCard key={h.sourceId} health={h} />
          ))}
        </div>
      )}
    </div>
  );
}
