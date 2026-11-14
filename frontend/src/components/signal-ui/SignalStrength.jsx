import React from "react";
import { cn } from "@/lib/utils";
import { SIGNAL_STROKES, signalStrength } from "./signalStrengthModel";
import "./signal-ui.css";

// Signal strength of one story for the new consumer UI (#462). Renders inside a
// `.signal-ui` scope. Distinct from shell/SignalMark, the Ops logo.
export default function SignalStrength({ decision, className = "" }) {
  const { filled, alert, label } = signalStrength(decision);
  return (
    <span
      className={cn("sg-strength", className)}
      role="img"
      aria-label={label}
      title={label}
      data-alert={alert || undefined}
    >
      {Array.from({ length: SIGNAL_STROKES }, (_, index) => (
        <i key={index} className="sg-strength__stroke" data-filled={index < filled || undefined} />
      ))}
    </span>
  );
}
