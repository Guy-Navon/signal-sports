import React from "react";
import { cn } from "@/lib/utils";

// A short editorial framing line for product pages — a tracked kicker label
// plus one sentence in the desk's voice. Sits directly on the atmosphere
// (no card), the same way the Feed's kickers do. Product pages only.
export default function DeskIntro({ kicker, children, className = "" }) {
  return (
    <p className={cn("text-sm leading-relaxed", className)}>
      {kicker && (
        <span className="text-[11px] font-semibold tracking-wide text-signal-ai me-2">
          {kicker} ·
        </span>
      )}
      <span className="text-text-secondary">{children}</span>
    </p>
  );
}
