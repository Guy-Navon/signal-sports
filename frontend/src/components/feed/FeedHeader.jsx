import React from "react";
import { cn } from "@/lib/utils";
import PulseDot from "@/components/shared/PulseDot";
import MonoValue from "@/components/shared/MonoValue";

// Consumer feed header: title, profile context, and a one-line "signal summary"
// that replaces the old QA-style 4-column stats grid.
function SummaryItem({ tone, count, label }) {
  if (!count) return null;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-text-secondary">
      <PulseDot tone={tone} pulse={tone === "push"} />
      <MonoValue className="text-foreground font-semibold">{count}</MonoValue>
      {label}
    </span>
  );
}

export default function FeedHeader({ profileName = "", total, counts, className = "" }) {
  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-display text-3xl font-bold text-foreground leading-tight">
            הסיגנל שלך
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            <MonoValue className="text-text-secondary">{total}</MonoValue> סיפורים רלוונטיים
            {profileName ? ` · ${profileName}` : ""}
          </p>
        </div>
      </div>

      {/* Signal summary strip */}
      <div className="flex items-center gap-x-4 gap-y-1 flex-wrap">
        <SummaryItem tone="push" count={counts.push} label="דורשים תשומת לב" />
        <SummaryItem tone="high" count={counts.high_feed} label="חשובים" />
        <SummaryItem tone="feed" count={counts.feed} label="רגילים" />
        <SummaryItem tone="low" count={counts.low_feed} label="ברקע" />
      </div>
    </div>
  );
}
