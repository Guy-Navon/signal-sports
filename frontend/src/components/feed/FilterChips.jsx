import React from "react";
import { cn } from "@/lib/utils";
import { FILTER_CHIPS } from "@/components/feed/feedFilters";

export default function FilterChips({ activeFilters, onToggle, counts = {} }) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-hide">
      {FILTER_CHIPS.map((chip) => {
        const active = activeFilters.has(chip.id);
        const count = counts[chip.id];
        return (
          <button
            key={chip.id}
            onClick={() => onToggle(chip.id)}
            className={cn(
              "flex-shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all",
              active
                ? "bg-signal-high/15 border-signal-high/40 text-signal-high"
                : "bg-surface-1 border-border text-text-secondary hover:border-text-dim hover:text-foreground"
            )}
          >
            {chip.label}
            {typeof count === "number" && count > 0 && (
              <span
                className={cn(
                  "text-[10px] tabular-nums rounded-full px-1.5 py-px",
                  active ? "bg-signal-high/20" : "bg-surface-3 text-text-dim"
                )}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
