import React, { useState } from "react";
import { Sparkles, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

// Distils the reasoning chain into a one-line "why this reached you" statement,
// with an inline expandable detail. The full chain lives in the Debug console.
function condensedReason(reasoning) {
  if (!reasoning || reasoning.length === 0) return null;
  // The engine emits a human-readable topic line: נושא: "מכבי תל אביב כדורסל" (...).
  // Prefer the quoted topic label — it directly answers "why does this matter to me".
  for (const line of reasoning) {
    const m = line.match(/נושא:\s*"([^"]+)"/);
    if (m) return m[1].trim();
  }
  // Otherwise fall back to the most specific non-final reasoning line.
  const meaningful = reasoning.filter((l) => !l.includes("החלטה סופית"));
  const finalLine = [...reasoning].reverse().find((l) => l.includes("החלטה סופית"));
  return (meaningful[meaningful.length - 1] || finalLine || reasoning[0]).trim();
}

export default function RelevanceReason({ reasoning = [], className = "" }) {
  const [open, setOpen] = useState(false);
  const summary = condensedReason(reasoning);
  if (!summary) return null;

  const steps = reasoning.slice(-4);
  const hasChain = reasoning.length > 0;

  const line = (
    <span className="inline-flex items-center gap-1.5 min-w-0">
      <Sparkles size={12} className="text-signal-ai flex-shrink-0" />
      <span className="truncate text-text-secondary">{summary}</span>
    </span>
  );

  if (!hasChain) {
    return <div className={cn("text-xs", className)}>{line}</div>;
  }

  return (
    <div className={cn("text-xs", className)}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="group flex items-center gap-1.5 min-w-0 text-start w-full hover:text-foreground transition-colors"
      >
        {line}
        <ChevronDown
          size={12}
          className={cn(
            "text-text-dim flex-shrink-0 transition-transform group-hover:text-text-secondary",
            open && "rotate-180"
          )}
        />
      </button>

      {open && (
        <div className="mt-2 ps-4 border-s-2 border-signal-ai/25">
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
