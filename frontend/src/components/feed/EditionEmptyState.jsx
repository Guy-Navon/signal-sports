import React from "react";
import SignalMark from "@/components/shell/SignalMark";

// The Feed's own empty moment — replaces the generic shared EmptyState
// (icon-in-circle) with something that feels like the desk is actively
// listening, not just "nothing here." Feed-specific only; components/shared
// EmptyState stays untouched for Debug/LLM QA.
export default function EditionEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center text-center py-24 px-4">
      <SignalMark className="scale-[2.2] mb-6" />
      <p className="text-[11px] font-semibold tracking-wide text-signal-feed">ממתין לאות</p>
      <h2 className="font-display text-xl font-bold text-foreground mt-2">אין סיגנלים חדשים</h2>
      <p className="text-sm text-text-secondary leading-relaxed mt-2 max-w-sm">
        המערכת סורקת את המקורות ברקע — סיפורים שרלוונטיים לפרופיל שלך יופיעו כאן.
      </p>
    </div>
  );
}
