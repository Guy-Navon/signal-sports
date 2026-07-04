import React from "react";
import { cn } from "@/lib/utils";
import MonoValue from "@/components/shared/MonoValue";

// Editorial section divider: small serif title + hairline rule + optional
// count and action slot. Replaces boxed section cards in the edition.
export default function SectionHeading({ children, count = null, action = null, className = "" }) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <h2 className="font-display text-lg font-bold text-foreground flex-shrink-0 flex items-baseline gap-2">
        {children}
        {typeof count === "number" && (
          <MonoValue className="text-xs font-normal text-text-dim">{count}</MonoValue>
        )}
      </h2>
      <div className="h-px flex-1 bg-border/70" aria-hidden />
      {action}
    </div>
  );
}
