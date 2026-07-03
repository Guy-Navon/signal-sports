import React, { useState, useEffect, useCallback } from "react";
import { Clock, Play, RefreshCw, AlertCircle } from "lucide-react";
import {
  getSchedulerStatus,
  getSourceHealth,
  runSchedulerNow,
  setSourceEnabled,
  isIngestionBusyError,
} from "@/api/client";
import {
  normalizeSchedulerStatusFromApi,
  normalizeSourceHealthFromApi,
} from "@/api/normalizers";
import SectionCard from "@/components/shared/SectionCard";
import HealthCard from "@/components/ops/HealthCard";
import { consoleButton, consoleAlert } from "@/components/ops/consoleStyles";

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
  ok: { label: "הצליח", className: "text-signal-high" },
  error: { label: "שגיאה", className: "text-signal-hidden" },
  skipped: { label: "דולג (ריצה פעילה)", className: "text-signal-push" },
  never_run: { label: "טרם רץ", className: "text-text-dim" },
};

export default function SchedulerPanel({ isBackendMode, onFeedRefresh }) {
  const [status, setStatus] = useState(null);
  const [health, setHealth] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [togglingSourceId, setTogglingSourceId] = useState(null);
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

  const handleToggleSource = async (sourceId, enabled) => {
    setTogglingSourceId(sourceId);
    setError(null);
    try {
      await setSourceEnabled(sourceId, enabled);
    } catch (err) {
      setError(err.message);
    } finally {
      setTogglingSourceId(null);
      loadStatus();
    }
  };

  // Backend-only feature — hidden in local mode (IngestionPanel explains why).
  if (!isBackendMode) return null;

  const runActive = isRunning || status?.activeRun != null;
  const lastStatusInfo = LAST_STATUS_LABELS[status?.lastStatus] ?? LAST_STATUS_LABELS.never_run;

  return (
    <SectionCard title="סטטוס ייבוא אוטומטי" icon={Clock}>
      <div className="space-y-4">
        {error && (
          <div className={consoleAlert("warn")}>
            <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {status && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
            <span className="text-text-dim">
              תזמון:{" "}
              <span className={status.enabled ? "text-signal-high" : "text-text-secondary"}>
                {status.enabled ? `פעיל — כל ${status.intervalMinutes} דקות` : "כבוי"}
              </span>
            </span>
            {status.enabled && status.nextRunAt && (
              <span className="text-text-dim">
                ריצה הבאה: <span className="text-text-secondary">{formatDateTime(status.nextRunAt)}</span>
              </span>
            )}
            <span className="text-text-dim">
              ריצה אחרונה: <span className="text-text-secondary">{formatDateTime(status.lastStartedAt)}</span>{" "}
              <span className={lastStatusInfo.className}>({lastStatusInfo.label})</span>
            </span>
            {status.lastError && (
              <span className="text-signal-hidden/80 truncate max-w-full">
                שגיאה אחרונה: {status.lastError}
              </span>
            )}
          </div>
        )}

        <button onClick={handleRunNow} disabled={runActive} className={consoleButton("primary")}>
          {runActive ? (
            <><RefreshCw size={14} className="animate-spin" /> ייבוא פעיל כרגע</>
          ) : (
            <><Play size={14} /> הרץ עכשיו</>
          )}
        </button>

        {health.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs text-text-dim font-medium">בריאות מקורות</div>
            {health.map((h) => (
              <HealthCard
                key={h.sourceId}
                health={h}
                onToggle={handleToggleSource}
                isToggling={togglingSourceId === h.sourceId}
              />
            ))}
          </div>
        )}
      </div>
    </SectionCard>
  );
}
