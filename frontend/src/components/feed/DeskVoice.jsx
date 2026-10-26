import React, { useState } from "react";
import { Sparkles, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { deskVoiceView } from "@/components/feed/deskVoiceModel";

// The desk's voice: "why you're seeing this" in one line. A reader sees the Hebrew
// reason the backend built from the deciding step (`reason`), or nothing (journey audit
// D6). Ops (`showTrace`: admin, local QA) keep the engine line with its expandable steps;
// the full trace stays in the Debug console.
//
// variant="full"  — "למה אצלך: <topic>" sentence + expandable steps (lead, bulletins)
// variant="line"  — quiet single line, still expandable (editorial, stream detail)
export default function DeskVoice({
  reasoning = [], reason = null, showTrace = true, variant = "line", className = "",
}) {
  const [open, setOpen] = useState(false);
  const view = deskVoiceView({ showTrace, reason, reasoning });
  if (!view) return null;

  const isFull = variant === "full";
  const summary = view.text;
  const steps = view.steps;

  if (view.mode === "reader") {
    return (
      <p className={cn("flex items-center gap-1.5 min-w-0", isFull ? "text-sm" : "text-xs", className)}>
        <Sparkles size={isFull ? 14 : 12} className="text-signal-ai flex-shrink-0" aria-hidden />
        <span className={cn("line-clamp-2 break-words", isFull ? "text-text-secondary" : "text-text-dim")}>
          {isFull && <span className="text-signal-ai/90 font-medium">למה אצלך: </span>}
          {summary}
        </span>
      </p>
    );
  }

  return (
    <div className={cn(isFull ? "text-sm" : "text-xs", className)}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="group flex items-center gap-1.5 min-w-0 max-w-full text-start hover:text-foreground transition-colors"
      >
        <Sparkles size={isFull ? 14 : 12} className="text-signal-ai flex-shrink-0" />
        {/* Clamped to one line rather than `truncate`. `truncate` is
            white-space: nowrap + ellipsis, which cuts at whatever character
            lands on the boundary — in this mixed-direction string that sliced
            the LTR run mid-token and rendered "(negotiation)" as "egotiation)".
            A one-line clamp wraps first, so the break lands between tokens. */}
        <span
          className={cn(
            "line-clamp-1 break-words",
            isFull ? "text-text-secondary" : "text-text-dim"
          )}
        >
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
