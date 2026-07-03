import React from "react";
import { RefreshCw, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { freshnessBadge, sourceTypeLabel } from "@/api/normalizers";
import MonoValue from "@/components/shared/MonoValue";

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

// Per-source health tile: freshness, type, pilot state, run counters + toggle.
export default function HealthCard({ health, onToggle, isToggling }) {
  const badge = freshnessBadge(health.freshness);
  const hasCounts = health.lastFetchedCount != null;

  return (
    <div
      className={cn(
        "rounded-[10px] border border-border p-3",
        health.enabled ? "bg-surface-2" : "bg-surface-1 opacity-70"
      )}
    >
      <div className="flex items-center gap-2 flex-wrap mb-1.5">
        <span className="text-xs font-medium text-foreground">{health.displayName}</span>
        <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full border", badge.colorClass)}>
          {badge.label}
        </span>
        <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-border bg-surface-3 text-text-secondary">
          {sourceTypeLabel(health.sourceType)}
        </span>
        {health.isPilot && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-signal-ai/30 bg-signal-ai/10 text-signal-ai">
            פיילוט
          </span>
        )}
        <button
          onClick={() => onToggle(health.sourceId, !health.enabled)}
          disabled={isToggling}
          className={cn(
            "ms-auto flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border transition-colors disabled:cursor-not-allowed disabled:opacity-50",
            health.enabled
              ? "bg-signal-high/10 border-signal-high/30 text-signal-high hover:bg-signal-high/20"
              : "bg-surface-3 border-border text-text-dim hover:text-text-secondary"
          )}
          title={health.enabled ? "כבה מקור" : "הפעל מקור"}
        >
          {isToggling ? (
            <RefreshCw size={10} className="animate-spin" />
          ) : health.enabled ? (
            <><CheckCircle2 size={10} /> פעיל</>
          ) : (
            <><XCircle size={10} /> כבוי</>
          )}
        </button>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-text-dim">
        <span>
          ריצה אחרונה: <span className="text-text-secondary">{formatDateTime(health.lastRunAt)}</span>
        </span>
        {hasCounts && (
          <span className="flex items-center gap-1">
            נמצאו <MonoValue className="text-text-secondary">{health.lastFetchedCount}</MonoValue> · נוספו{" "}
            <MonoValue className={health.lastInsertedCount > 0 ? "text-signal-high" : "text-text-secondary"}>
              {health.lastInsertedCount}
            </MonoValue>{" "}· נכשלו{" "}
            <MonoValue className={health.lastFailedCount > 0 ? "text-signal-hidden" : "text-text-secondary"}>
              {health.lastFailedCount}
            </MonoValue>
          </span>
        )}
        {health.consecutiveFailures > 0 && (
          <span className="text-signal-hidden">{health.consecutiveFailures} כשלונות רצופים</span>
        )}
      </div>
      {health.lastErrorMessage && (
        <div className="mt-1 text-xs text-signal-hidden/80 truncate">{health.lastErrorMessage}</div>
      )}
    </div>
  );
}
