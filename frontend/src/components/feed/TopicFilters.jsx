import React from "react";
import { cn } from "@/lib/utils";
import { TOPIC_CHIPS } from "@/components/feed/feedFilters";

// Quiet topic filters under the spectrum — text toggles, not pill chips.
export default function TopicFilters({ activeFilters, onToggle, onReset, className = "" }) {
  const anyActive = !activeFilters.has("all");

  return (
    <div className={cn("flex items-center flex-wrap gap-x-4 gap-y-1 text-xs", className)}>
      <span className="text-text-dim">סינון:</span>
      {TOPIC_CHIPS.map((chip) => {
        const active = activeFilters.has(chip.id);
        return (
          <button
            key={chip.id}
            onClick={() => onToggle(chip.id)}
            aria-pressed={active}
            className={cn(
              "transition-colors underline-offset-4",
              active
                ? "text-signal-high underline decoration-signal-high/50"
                : "text-text-secondary hover:text-foreground"
            )}
          >
            {chip.label}
          </button>
        );
      })}
      {anyActive && (
        <button
          onClick={onReset}
          className="text-text-dim hover:text-foreground transition-colors ms-2"
        >
          ✕ נקה הכל
        </button>
      )}
    </div>
  );
}
