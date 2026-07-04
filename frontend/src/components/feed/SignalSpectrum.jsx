import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";
import MonoValue from "@/components/shared/MonoValue";

// The signal spectrum: today's relevance distribution as a segmented light
// bar. Segment widths are proportional to the level counts; each segment and
// its legend entry toggle that level as a filter. Status display, brand
// moment, and control in one artifact — replaces the counts strip + level
// filter chips.
const SEGMENTS = [
  { id: "push", label: "דורשים תשומת לב", bar: "bg-signal-push", dot: "bg-signal-push", pulse: true },
  { id: "high_feed", label: "חשובים", bar: "bg-signal-high", dot: "bg-signal-high", pulse: false },
  { id: "feed", label: "בזרם", bar: "bg-signal-feed/80", dot: "bg-signal-feed", pulse: false },
  { id: "low_feed", label: "ברקע", bar: "bg-signal-low/50", dot: "bg-signal-low", pulse: false },
];

export default function SignalSpectrum({
  counts,
  activeFilters,
  onToggle,
  vertical = false,
  className = "",
}) {
  const reduce = useReducedMotion();
  const present = SEGMENTS.filter((s) => (counts[s.id] || 0) > 0);
  const anyLevelActive = SEGMENTS.some((s) => activeFilters.has(s.id));
  if (!present.length) return null;

  return (
    <div className={className}>
      <div className="flex h-1.5 rounded-full overflow-hidden gap-[3px]" role="group" aria-label="ספקטרום הסיגנל">
        {present.map((seg, i) => {
          const active = activeFilters.has(seg.id);
          const dimmed = anyLevelActive && !active;
          return (
            <motion.button
              key={seg.id}
              onClick={() => onToggle(seg.id)}
              aria-label={`${counts[seg.id]} ${seg.label}`}
              aria-pressed={active}
              title={`${counts[seg.id]} ${seg.label}`}
              initial={reduce ? false : { scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ duration: 0.55, delay: 0.15 + i * 0.09, ease: [0.22, 1, 0.36, 1] }}
              // flex-grow carries the proportion; CSS transition animates later
              // recomposition. RTL-only app: segments grow from the right edge.
              style={{ flexGrow: counts[seg.id], transformOrigin: "100% 50%" }}
              className={cn(
                "min-w-[16px] rounded-full transition-all duration-500",
                seg.bar,
                dimmed && "opacity-25",
                active && "shadow-[0_0_8px_currentColor]"
              )}
            />
          );
        })}
      </div>

      <div
        className={cn(
          "mt-2.5",
          vertical
            ? "flex flex-col gap-2"
            : "flex items-center flex-wrap gap-x-4 gap-y-1"
        )}
      >
        {present.map((seg) => {
          const active = activeFilters.has(seg.id);
          const dimmed = anyLevelActive && !active;
          return (
            <button
              key={seg.id}
              onClick={() => onToggle(seg.id)}
              aria-pressed={active}
              className={cn(
                "inline-flex items-center gap-1.5 text-xs transition-colors",
                vertical && "justify-between w-full",
                active ? "text-foreground" : "text-text-secondary hover:text-foreground",
                dimmed && "opacity-50 hover:opacity-100"
              )}
            >
              <span className="inline-flex items-center gap-1.5">
                <span
                  aria-hidden
                  className={cn(
                    "inline-block w-1.5 h-1.5 rounded-full",
                    seg.dot,
                    seg.pulse && "animate-pulse-soft"
                  )}
                />
                {seg.label}
              </span>
              <MonoValue className={cn("font-semibold", active ? "text-foreground" : "text-text-secondary")}>
                {counts[seg.id]}
              </MonoValue>
            </button>
          );
        })}
      </div>
    </div>
  );
}
