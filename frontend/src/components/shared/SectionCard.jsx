import React from "react";
import { cn } from "@/lib/utils";

// Console panel: titled section with optional icon and actions slot.
export default function SectionCard({ title, icon: Icon, actions, children, className }) {
  return (
    <section
      className={cn(
        "bg-surface-1 border border-border rounded-[10px] elevation-1 overflow-hidden",
        className
      )}
    >
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border">
          <div className="flex items-center gap-2 min-w-0">
            {Icon && <Icon size={15} className="text-text-secondary flex-shrink-0" />}
            <h2 className="text-sm font-semibold text-foreground truncate">{title}</h2>
          </div>
          {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}
