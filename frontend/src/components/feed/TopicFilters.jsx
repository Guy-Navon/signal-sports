import React from "react";
import { cn } from "@/lib/utils";
import { TOPIC_CHIPS } from "@/components/feed/feedFilters";

// Quiet topic filters — text toggles, not pill chips. Inline row under the
// spectrum on small screens; vertical list inside the signal board on xl.
export default function TopicFilters({
  activeFilters,
  onToggle,
  onReset,
  vertical = false,
  className = "",
}) {
  const anyActive = !activeFilters.has("all");

  return (
    <div
      className={cn(
        vertical
          ? "flex flex-col items-start gap-2 text-xs"
          : "flex items-center flex-wrap gap-x-4 gap-y-1 text-xs",
        className
      )}
    >
      {!vertical && <span className="text-text-dim">סינון:</span>}
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
          className={cn(
            "text-text-dim hover:text-foreground transition-colors",
            !vertical && "ms-2"
          )}
        >
          ✕ נקה הכל
        </button>
      )}
    </div>
  );
}
