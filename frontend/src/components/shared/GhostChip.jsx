import React from "react";
import { cn } from "@/lib/utils";

// Quiet secondary metadata chip — visible on scan, silent otherwise.
export default function GhostChip({ children, className = "", ...props }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[11px] leading-4 text-text-secondary",
        "border border-border rounded-full px-2 py-0.5 bg-transparent",
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}
