import React from "react";
import { cn } from "@/lib/utils";

export default function EmptyState({ icon: Icon = null, title, hint = null, action = null, className = "" }) {
  return (
    <div className={cn("flex flex-col items-center justify-center text-center py-16 px-4", className)}>
      {Icon && (
        <div className="w-12 h-12 rounded-full bg-surface-2 border border-border flex items-center justify-center mb-4">
          <Icon size={20} className="text-text-dim" />
        </div>
      )}
      <p className="text-base font-medium text-foreground">{title}</p>
      {hint && <p className="text-sm text-text-secondary mt-1 max-w-sm">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
