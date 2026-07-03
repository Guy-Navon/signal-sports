import React from "react";
import { cn } from "@/lib/utils";
import { getDecisionConfig } from "@/components/feed/decisionConfig";

// The "signal light": a vertical bar on the card's inline-start edge whose
// colour and glow encode relevance. Gold + glow is reserved for push.
export default function SignalRail({ decision }) {
  const config = getDecisionConfig(decision);
  if (config.rail === "bg-transparent") return null;
  return (
    <span
      aria-hidden
      className={cn(
        "absolute inset-y-3 start-0 w-[3px] rounded-full transition-all",
        config.rail,
        config.railGlow &&
          "shadow-[0_0_10px_hsl(var(--signal-push)/0.6)] group-hover:shadow-[0_0_16px_hsl(var(--signal-push)/0.8)]"
      )}
    />
  );
}
