import React from "react";
import { cn } from "@/lib/utils";

export default function PageHeader({ title, subtitle = null, icon: Icon = null, children = null, className = "" }) {
  return (
    <div className={cn("flex items-start justify-between gap-4 mb-6", className)}>
      <div className="min-w-0">
        <h1 className="font-display text-2xl font-bold text-foreground leading-tight flex items-center gap-2">
          {Icon && <Icon size={20} className="text-text-dim" />}
          {title}
        </h1>
        {subtitle && <p className="text-sm text-text-secondary mt-1">{subtitle}</p>}
      </div>
      {children && <div className="flex items-center gap-2 flex-shrink-0">{children}</div>}
    </div>
  );
}
