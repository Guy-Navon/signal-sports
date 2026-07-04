import React from "react";
import { cn } from "@/lib/utils";
import MonoValue from "@/components/shared/MonoValue";

// Editorial section divider: small tracked label + hairline rule + optional
// count and action slot. Deliberately Heebo (not serif) — the serif voice is
// reserved for story headlines; labels stay modern and quiet.
export default function SectionHeading({ children, count = null, action = null, className = "" }) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <h2 className="text-[11px] font-semibold tracking-[0.14em] text-text-secondary flex-shrink-0 flex items-baseline gap-2">
        {children}
        {typeof count === "number" && (
          <MonoValue className="text-[10px] font-normal text-text-dim">{count}</MonoValue>
        )}
      </h2>
      <div className="h-px flex-1 bg-border/60" aria-hidden />
      {action}
    </div>
  );
}
