import React from "react";
import { cn } from "@/lib/utils";

// Numbers, times, and IDs render LTR inside RTL text flow.
export default function MonoValue({ children, className }) {
  return (
    <span dir="ltr" className={cn("font-mono tabular-nums inline-block", className)}>
      {children}
    </span>
  );
}
