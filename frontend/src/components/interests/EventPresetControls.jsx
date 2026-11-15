import React from "react";
import "./interests.css";
import {
  EVENT_PRESET_GROUPS,
  PRESET_STATES,
} from "@/components/interests/interestsModel";

// The 5 global event-preference presets, three-state each (פחות/רגיל/יותר).
// Groups expand server-side into existing event types (docs/INTERESTS.md) —
// this control never invents event vocabulary.
export default function EventPresetControls({ value, onChange }) {
  return (
    <div className="sg-event-presets">
      {EVENT_PRESET_GROUPS.map((group) => {
        const current = value?.[group.id] || "normal";
        return (
          <div
            key={group.id}
            className="sg-event-preset"
          >
            <span>{group.label}</span>
            <div className="sg-event-preset__choices" role="group" aria-label={group.label}>
              {PRESET_STATES.map((state) => (
                <button
                  key={state.id}
                  type="button"
                  onClick={() => onChange({ ...value, [group.id]: state.id })}
                  aria-pressed={current === state.id}
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
