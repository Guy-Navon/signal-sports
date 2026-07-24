import React from "react";
import { cn } from "@/lib/utils";

// The wordmark icon: three ascending signal bars, the middle one breathing.
// Same visual language as the Feed's SIGNAL strength instrument (LeadStory) —
// the brand mark and the product's relevance indicator are the same idea.
export default function SignalMark({ className = "" }) {
  return (
    <span className={cn("inline-flex h-5 items-end gap-[2px]", className)} aria-hidden>
      <span className="h-[7px] w-[3px] bg-signal-feed" />
      <span className="h-[12px] w-[3px] bg-signal-high" />
      <span className="h-[17px] w-[3px] bg-signal-push" />
      <span className="h-[10px] w-[3px] bg-background/70" />
    </span>
  );
}
