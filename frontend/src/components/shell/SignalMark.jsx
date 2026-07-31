import React from "react";
import { cn } from "@/lib/utils";

// The wordmark icon: three ascending signal bars.
// Same visual language as the Orbit field's signal-strength meter — the brand
// mark and the product's relevance indicator are the same idea.
export default function SignalMark({ className = "" }) {
  return (
    <span className={cn("inline-flex items-end gap-[2.5px]", className)} aria-hidden>
      <span className="w-[3px] h-[8px] rounded-full bg-signal-feed" />
      <span className="w-[3px] h-[13px] rounded-full bg-signal-high" />
      <span className="w-[3px] h-[10px] rounded-full bg-signal-feed" />
    </span>
  );
}
