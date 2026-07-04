import React from "react";
import { cn } from "@/lib/utils";
import MonoValue from "@/components/shared/MonoValue";

const TONE_TEXT = {
  push: "text-signal-push",
  high: "text-signal-high",
  feed: "text-signal-feed",
  low: "text-signal-low",
  hidden: "text-signal-hidden",
  ai: "text-signal-ai",
  neutral: "text-foreground",
};

// Mono (LTR) is right for numeric stats but mangles Hebrew text values, so
// only numeric-looking values get the mono treatment.
function isNumericValue(v) {
  return typeof v === "number" || (typeof v === "string" && /^[\d.,/%+\-\s]+$/.test(v));
}

export default function StatCard({ label, value, tone = "neutral", hint = null, className = "" }) {
  const toneClass = TONE_TEXT[tone] || TONE_TEXT.neutral;
  return (
    <div
      className={cn(
        "bg-surface-1 border border-border rounded-[10px] px-4 py-3 elevation-1",
        className
      )}
    >
      {isNumericValue(value) ? (
        <MonoValue className={cn("text-xl font-semibold", toneClass)}>{value}</MonoValue>
      ) : (
        <span className={cn("block text-xl font-semibold", toneClass)}>{value}</span>
      )}
      <p className="text-xs text-text-secondary mt-0.5">{label}</p>
      {hint && <p className="text-[11px] text-text-dim mt-1">{hint}</p>}
    </div>
  );
}
