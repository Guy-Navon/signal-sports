import React from "react";
import { Star } from "lucide-react";
import { cn } from "@/lib/utils";

// One selectable scope chip: tap = Follow/unfollow; star = "אל תפספס לי".
// Disabled (non-selectable) chips render as "בקרוב" — visible, not followable.
export default function FollowChip({
  label, followed, starred, selectable = true, onToggle, onStar,
}) {
  if (!selectable) {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs border border-border/60 text-text-dim/60 cursor-not-allowed select-none">
        {label}
        <span className="text-[10px]">בקרוב</span>
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full text-xs border transition-colors select-none",
        followed
          ? starred
            ? "border-signal-push/50 bg-signal-push/10 text-signal-push"
            : "border-signal-high/50 bg-signal-high/10 text-signal-high"
          : "border-border text-text-secondary hover:border-text-dim",
      )}
    >
      <button type="button" onClick={onToggle} className="ps-3 py-1.5 pe-1">
        {label}
      </button>
      {followed && (
        <button
          type="button"
          onClick={onStar}
          title={starred ? "עדיפות רגילה" : "אל תפספס לי"}
          aria-pressed={starred}
          className="pe-2.5 py-1.5"
        >
          <Star size={12} className={starred ? "fill-current" : ""} />
        </button>
      )}
    </span>
  );
}
