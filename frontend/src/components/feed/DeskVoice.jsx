import React, { useState } from "react";
import { Sparkles, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { condensedReason } from "@/components/feed/storyLabels";

// The desk's voice: "why you're seeing this" in one spoken line, with the
// reasoning steps available as an expandable margin note. The full trace
// stays in the Debug console.
//
// variant="full"  — "למה אצלך: <topic>" sentence + expandable steps (lead, bulletins)
// variant="line"  — quiet single line, still expandable (editorial, stream detail)
export default function DeskVoice({ reasoning = [], variant = "line", className = "" }) {
  const [open, setOpen] = useState(false);
  const summary = condensedReason(reasoning);
  if (!summary) return null;

  const isFull = variant === "full";
  const steps = reasoning.slice(-4);

  return (
    <div className={cn(isFull ? "text-sm" : "text-xs", className)}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="group flex items-center gap-1.5 min-w-0 max-w-full text-start hover:text-foreground transition-colors"
      >
        <Sparkles size={isFull ? 14 : 12} className="text-signal-ai flex-shrink-0" />
        <span className={cn("truncate", isFull ? "text-text-secondary" : "text-text-dim")}>
          {isFull && <span className="text-signal-ai/90 font-medium">למה אצלך: </span>}
          {summary}
        </span>
        <ChevronDown
          size={12}
          className={cn(
            "text-text-dim flex-shrink-0 transition-transform group-hover:text-text-secondary",
            open && "rotate-180"
          )}
        />
      </button>

      {open && (
        <div className="mt-2 ps-4 border-s-2 border-signal-ai/25 text-xs">
          <ol className="space-y-1">
            {steps.map((step, i) => {
              const isFinal = step.includes("החלטה סופית");
              return (
                <li
                  key={i}
                  className={cn(
                    "leading-relaxed",
                    isFinal ? "text-foreground font-medium" : "text-text-secondary"
                  )}
                >
                  {step}
                </li>
              );
            })}
          </ol>
          {reasoning.length > 4 && (
            <p className="text-[10px] text-text-dim mt-1.5">
              +{reasoning.length - 4} שלבים נוספים — ראה קונסולת דיבאג לפירוט מלא
            </p>
          )}
        </div>
      )}
    </div>
  );
}
