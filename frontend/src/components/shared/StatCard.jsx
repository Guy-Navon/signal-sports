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

export default function StatCard({ label, value, tone = "neutral", hint, className }) {
  return (
    <div
      className={cn(
        "bg-surface-1 border border-border rounded-[10px] px-4 py-3 elevation-1",
        className
      )}
    >
      <MonoValue className={cn("text-xl font-semibold", TONE_TEXT[tone] || TONE_TEXT.neutral)}>
        {value}
      </MonoValue>
      <p className="text-xs text-text-secondary mt-0.5">{label}</p>
      {hint && <p className="text-[11px] text-text-dim mt-1">{hint}</p>}
    </div>
  );
}
