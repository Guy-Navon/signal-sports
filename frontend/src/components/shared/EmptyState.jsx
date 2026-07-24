import React from "react";
import { cn } from "@/lib/utils";

export default function EmptyState({ icon: Icon = null, title, hint = null, action = null, className = "" }) {
  return (
    <div className={cn("ledger-panel flex flex-col items-center justify-center px-5 py-14 text-center", className)}>
      {Icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center bg-foreground text-background">
          <Icon size={20} />
        </div>
      )}
      <p className="font-display text-xl font-bold text-foreground">{title}</p>
      {hint && <p className="text-sm text-text-secondary mt-1 max-w-sm">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
