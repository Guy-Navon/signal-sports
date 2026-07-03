import React from "react";
import { cn } from "@/lib/utils";

function shimmer(className) {
  return cn(
    "rounded-md bg-gradient-to-l from-surface-2 via-surface-3 to-surface-2",
    "bg-[length:200%_100%] animate-shimmer",
    className
  );
}

function CardSkeleton() {
  return (
    <div className="bg-surface-1 border border-border rounded-[14px] p-5 elevation-1">
      <div className="flex items-center gap-2 mb-3">
        <div className={shimmer("h-3 w-16")} />
        <div className={shimmer("h-3 w-24")} />
      </div>
      <div className={shimmer("h-5 w-4/5 mb-2")} />
      <div className={shimmer("h-4 w-3/5 mb-4")} />
      <div className="flex items-center gap-2">
        <div className={shimmer("h-4 w-14 rounded-full")} />
        <div className={shimmer("h-4 w-14 rounded-full")} />
      </div>
    </div>
  );
}

function RowSkeleton() {
  return (
    <div className="bg-surface-1 border border-border rounded-[10px] px-4 py-3 flex items-center gap-3">
      <div className={shimmer("h-2.5 w-2.5 rounded-full flex-shrink-0")} />
      <div className={shimmer("h-4 flex-1")} />
      <div className={shimmer("h-4 w-16 flex-shrink-0")} />
    </div>
  );
}

function StatSkeleton() {
  return (
    <div className="bg-surface-1 border border-border rounded-[10px] px-4 py-3">
      <div className={shimmer("h-6 w-10 mb-2")} />
      <div className={shimmer("h-3 w-16")} />
    </div>
  );
}

const VARIANTS = { card: CardSkeleton, row: RowSkeleton, stat: StatSkeleton };

export default function LoadingSkeleton({ variant = "card", count = 3, className }) {
  const Item = VARIANTS[variant] || CardSkeleton;
  return (
    <div className={cn("space-y-3", className)} aria-busy="true">
      {Array.from({ length: count }, (_, i) => (
        <Item key={i} />
      ))}
    </div>
  );
}
