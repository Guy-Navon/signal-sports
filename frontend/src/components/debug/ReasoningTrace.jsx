import React from "react";
import { cn } from "@/lib/utils";

// Numbered decision chain rendered as a console "trace": each step on a hairline
// rail, with the final decision highlighted by tone.
export default function ReasoningTrace({ reasoning = [], numbered = true }) {
  if (!reasoning.length) return null;
  return (
    <div className="space-y-1">
      {reasoning.map((line, i) => {
        const isDecision = line.includes("החלטה סופית");
        const isHidden = line.includes("מוסתר") || line.includes("hidden");
        const isPositive =
          line.includes("push") || line.includes("דורש תשומת לב") || line.includes("חשוב");
        return (
          <div
            key={i}
            className={cn(
              "text-xs leading-relaxed px-2 py-1 rounded border-e-2",
              isDecision
                ? isHidden
                  ? "text-signal-hidden bg-signal-hidden/10 border-signal-hidden"
                  : isPositive
                    ? "text-signal-push bg-signal-push/10 border-signal-push"
                    : "text-signal-high bg-signal-high/10 border-signal-high"
                : "text-text-secondary bg-surface-2 border-border"
            )}
          >
            {numbered ? `${i + 1}. ` : ""}
            {line}
          </div>
        );
      })}
    </div>
  );
}
