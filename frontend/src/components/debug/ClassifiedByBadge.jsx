import React from "react";
import { cn } from "@/lib/utils";
import { classifiedByClass } from "@/components/debug/classifiedByConfig";

export default function ClassifiedByBadge({ value }) {
  return (
    <span className={cn("text-[10px] border rounded-full px-1.5 py-0.5 font-mono", classifiedByClass(value))}>
      {value}
    </span>
  );
}
