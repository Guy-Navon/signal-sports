import React from "react";
import GhostChip from "@/components/shared/GhostChip";

// Secondary metadata (entities / tags) rendered as quiet ghost chips.
export default function EntityChips({ items = [], max = 3, className = "" }) {
  const shown = items.filter(Boolean).slice(0, max);
  if (shown.length === 0) return null;
  return (
    <div className={className}>
      <div className="flex flex-wrap gap-1.5">
        {shown.map((item) => (
          <GhostChip key={item}>{item}</GhostChip>
        ))}
      </div>
    </div>
  );
}
