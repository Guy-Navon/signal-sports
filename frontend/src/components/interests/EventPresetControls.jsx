import React from "react";
import { cn } from "@/lib/utils";
import {
  EVENT_PRESET_GROUPS,
  PRESET_STATES,
} from "@/components/interests/interestsModel";

// The 5 global event-preference presets, three-state each (פחות/רגיל/יותר).
// Groups expand server-side into existing event types (docs/INTERESTS.md) —
// this control never invents event vocabulary.
export default function EventPresetControls({ value, onChange }) {
  return (
    <div className="space-y-2">
      {EVENT_PRESET_GROUPS.map((group) => {
        const current = value?.[group.id] || "normal";
        return (
          <div
            key={group.id}
            className="flex items-center justify-between gap-3 bg-surface-1 border border-border rounded-[10px] px-3 py-2"
          >
            <span className="text-sm text-foreground">{group.label}</span>
            <div className="flex gap-1">
              {PRESET_STATES.map((state) => (
                <button
                  key={state.id}
                  type="button"
                  onClick={() => onChange({ ...value, [group.id]: state.id })}
                  className={cn(
                    "px-2.5 py-1 rounded-full text-xs border transition-colors",
                    current === state.id
                      ? state.id === "more"
                        ? "border-signal-high/50 bg-signal-high/10 text-signal-high"
                        : state.id === "less"
                          ? "border-signal-hidden/40 bg-signal-hidden/10 text-signal-hidden"
                          : "border-text-dim/50 bg-surface-2 text-text-secondary"
                      : "border-border text-text-dim hover:border-text-dim",
                  )}
                >
                  {state.label}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
