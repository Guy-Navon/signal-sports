import React from "react";
import { cn } from "@/lib/utils";
import PulseDot from "@/components/shared/PulseDot";

export default function DataModeBadge({ isBackendMode, className }) {
  return (
    <span
      title={isBackendMode ? "מצב נתונים: שרת" : "מצב נתונים: מקומי"}
      className={cn(
        "inline-flex items-center gap-1.5 text-[10px] px-2 py-0.5 rounded-full border font-medium",
        isBackendMode
          ? "bg-signal-high/10 border-signal-high/25 text-signal-high"
          : "bg-surface-2 border-border text-text-secondary",
        className
      )}
    >
      <PulseDot tone={isBackendMode ? "high" : "neutral"} pulse={isBackendMode} />
      {isBackendMode ? "שרת חי" : "מצב מקומי"}
    </span>
  );
}
