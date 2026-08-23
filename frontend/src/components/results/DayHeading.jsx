import React from "react";
import { cn } from "@/lib/utils";
import MonoValue from "@/components/shared/MonoValue";

// Day divider for the Results list: small tracked label + hairline rule + game
// count. Previously `components/feed/SectionHeading`, which Orbit removed along
// with the rest of the Edition feed composition; Results was its only remaining
// caller, so the component now lives with the feature that uses it.
export default function DayHeading({ children, count = null, className = "" }) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <h2 className="text-[11px] font-semibold tracking-[0.14em] text-text-secondary flex-shrink-0 flex items-baseline gap-2">
        {children}
        {typeof count === "number" && (
          <MonoValue className="text-[10px] font-normal text-text-dim">{count}</MonoValue>
        )}
      </h2>
      <div className="h-px flex-1 bg-border/60" aria-hidden />
    </div>
  );
}
