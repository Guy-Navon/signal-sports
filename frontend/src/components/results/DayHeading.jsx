import React from "react";
import { cn } from "@/lib/utils";

// Part B section heading and a quiet, tabular game count.
export default function DayHeading({ children, count = null, className = "" }) {
  return (
    <div className={cn("sg-results-page__day", className)}>
      <h2>
        {children}
        {typeof count === "number" && (
          <span className="sg-results-page__count" dir="ltr">{count}</span>
        )}
      </h2>
    </div>
  );
}
