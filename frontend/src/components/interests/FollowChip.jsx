import React from "react";
import { Check, Star } from "lucide-react";
import SignalStrength from "@/components/signal-ui/SignalStrength";

// One selectable scope chip: tap = Follow/unfollow; star = "אל תפספס לי".
// Disabled (non-selectable) chips render as "בקרוב" — visible, not followable.
export default function FollowChip({
  label, followed, starred, selectable = true, onToggle, onStar,
}) {
  if (!selectable) {
    return (
      <span className="sg-interest-row" aria-disabled="true">
        <bdi dir="auto">{label}</bdi>
        <small>בקרוב</small>
      </span>
    );
  }
  return (
    <span className="sg-interest-row" data-followed={followed || undefined}>
      <button type="button" onClick={onToggle} aria-pressed={followed} className="sg-interest-row__pick">
        {followed ? <Check size={16} aria-hidden="true" /> : <span className="sg-interest-row__check" aria-hidden="true" />}
        <bdi dir="auto">{label}</bdi>
      </button>
      {followed && (
        <button
          type="button"
          onClick={onStar}
          title={starred ? "עדיפות רגילה" : "אל תפספס לי"}
          aria-label={`${starred ? "עדיפות רגילה" : "אל תפספס לי"}: ${label}`}
          aria-pressed={starred}
          className="sg-interest-row__star"
        >
          <SignalStrength decision={starred ? "push" : "high_feed"} />
          <Star size={14} className={starred ? "fill-current" : ""} aria-hidden="true" />
        </button>
      )}
    </span>
  );
}
