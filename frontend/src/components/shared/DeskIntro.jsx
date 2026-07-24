import React from "react";
import { cn } from "@/lib/utils";

// A short editorial framing line for product pages — a tracked kicker label
// plus one sentence in the desk's voice. Sits directly on the atmosphere
// (no card), the same way the Feed's kickers do. Product pages only.
export default function DeskIntro({ kicker, children, className = "" }) {
  return (
    <p className={cn("border-s-4 border-signal-push ps-4 text-sm leading-relaxed", className)}>
      {kicker && (
        <span className="me-2 font-mono text-[10px] font-bold tracking-[0.12em] text-signal-push">
          {kicker} ·
        </span>
      )}
      <span className="text-text-secondary">{children}</span>
    </p>
  );
}
