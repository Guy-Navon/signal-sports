import React from "react";
import { cn } from "@/lib/utils";

function shimmer(className) {
  return cn(
    "rounded-md bg-gradient-to-l from-surface-2 via-surface-3 to-surface-2",
    "bg-[length:200%_100%] animate-shimmer",
    className
  );
}

// Loading state that mirrors the edition's shape: masthead line, spectrum,
// lead headline, editorial blocks, stream rows. No card boxes.
export default function EditionSkeleton() {
  return (
    <div aria-busy="true" className="space-y-10">
      {/* Masthead */}
      <div>
        <div className={shimmer("h-3 w-56")} />
        <div className={shimmer("h-9 w-72 mt-3")} />
        <div className={shimmer("h-1.5 w-full rounded-full mt-6")} />
        <div className="flex gap-4 mt-3">
          <div className={shimmer("h-3 w-24")} />
          <div className={shimmer("h-3 w-16")} />
          <div className={shimmer("h-3 w-16")} />
        </div>
      </div>

      {/* Lead story */}
      <div>
        <div className={shimmer("h-3 w-32")} />
        <div className={shimmer("h-10 w-full mt-3")} />
        <div className={shimmer("h-10 w-3/4 mt-2")} />
        <div className={shimmer("h-4 w-2/3 mt-4")} />
        <div className="flex gap-4 mt-5">
          <div className={shimmer("h-8 w-28 rounded-full")} />
          <div className={shimmer("h-4 w-32 mt-2")} />
        </div>
      </div>

      {/* Editorial tier */}
      <div>
        <div className="flex items-center gap-3">
          <div className={shimmer("h-5 w-28")} />
          <div className="h-px flex-1 bg-border/50" />
        </div>
        <div className="grid gap-x-10 gap-y-8 md:grid-cols-2 mt-6">
          {[0, 1].map((i) => (
            <div key={i}>
              <div className={shimmer("h-3 w-24")} />
              <div className={shimmer("h-6 w-full mt-2")} />
              <div className={shimmer("h-6 w-2/3 mt-1.5")} />
              <div className={shimmer("h-3 w-40 mt-3")} />
            </div>
          ))}
        </div>
      </div>

      {/* Stream rows */}
      <div className="space-y-5">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="flex items-center justify-between gap-4">
            <div className="flex-1">
              <div className={shimmer("h-4 w-4/5")} />
              <div className={shimmer("h-3 w-48 mt-2")} />
            </div>
            <div className={shimmer("h-4 w-10 flex-shrink-0")} />
          </div>
        ))}
      </div>
    </div>
  );
}
