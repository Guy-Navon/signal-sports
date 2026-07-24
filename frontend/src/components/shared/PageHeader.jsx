import React from "react";
import { cn } from "@/lib/utils";

export default function PageHeader({
  title,
  subtitle = null,
  icon: Icon = null,
  kicker = "SIGNAL / PERSONAL DESK",
  children = null,
  className = "",
}) {
  return (
    <div className={cn("editorial-rule-heavy mb-7 flex items-start justify-between gap-4 pt-3", className)}>
      <div className="min-w-0">
        <div className="mb-2 flex items-center gap-2">
          {Icon && (
            <span className="inline-flex h-6 w-6 items-center justify-center bg-foreground text-background">
              <Icon size={13} />
            </span>
          )}
          <span className="eyebrow">{kicker}</span>
        </div>
        <h1 className="font-display text-[2.25rem] font-bold leading-none tracking-[-0.02em] text-foreground sm:text-[3rem]">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-text-secondary">{subtitle}</p>
        )}
      </div>
      {children && <div className="flex flex-shrink-0 items-center gap-2">{children}</div>}
    </div>
  );
}
