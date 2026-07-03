import React from "react";
import { cn } from "@/lib/utils";
import { getDecisionConfig } from "@/components/feed/decisionConfig";

// Compact pill showing a scored decision level, styled from the signal tokens.
export default function DecisionBadge({ decision, size = "sm", className = "" }) {
  const config = getDecisionConfig(decision);
  const Icon = config.icon;
  const xs = size === "xs";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border font-medium whitespace-nowrap",
        xs ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs",
        config.badge,
        className
      )}
    >
      <Icon size={xs ? 9 : 11} strokeWidth={2.5} />
      {config.label}
    </span>
  );
}
