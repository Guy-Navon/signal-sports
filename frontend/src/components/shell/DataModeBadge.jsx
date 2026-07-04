import React from "react";
import { cn } from "@/lib/utils";
import PulseDot from "@/components/shared/PulseDot";

// A quiet dot + tooltip — data mode is ops-relevant information, not a
// consumer-facing label, so it no longer competes with the wordmark for
// attention in the masthead.
export default function DataModeBadge({ isBackendMode, className = "" }) {
  return (
    <span
      title={isBackendMode ? "מצב נתונים: שרת" : "מצב נתונים: מקומי"}
      className={cn("inline-flex items-center justify-center p-1", className)}
    >
      <PulseDot tone={isBackendMode ? "high" : "neutral"} pulse={isBackendMode} />
    </span>
  );
}
