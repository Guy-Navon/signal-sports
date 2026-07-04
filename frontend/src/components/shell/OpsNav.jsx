import React from "react";
import { Link, useLocation } from "react-router-dom";
import { Terminal } from "lucide-react";
import { cn } from "@/lib/utils";
import { getOpsNavItems } from "@/components/shell/navConfig";

// Console strip shown above ops pages — marks the dev/QA area as distinct from the product.
export default function OpsNav({ isBackendMode }) {
  const location = useLocation();
  const opsItems = getOpsNavItems(isBackendMode);

  return (
    <div className="mb-6 bg-surface-1 border border-border rounded-[10px] px-3 py-2 flex items-center gap-3 overflow-x-auto">
      <div className="flex items-center gap-1.5 text-text-dim flex-shrink-0">
        <Terminal size={13} />
        <span className="text-[11px] font-medium">קונסולת תפעול</span>
      </div>
      <div className="h-4 border-s border-border flex-shrink-0" />
      <div className="flex items-center gap-1">
        {opsItems.map(({ path, label, icon: Icon }) => {
          const active = location.pathname === path;
          return (
            <Link
              key={path}
              to={path}
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs transition-colors whitespace-nowrap",
                active
                  ? "bg-surface-3 text-foreground font-medium"
                  : "text-text-secondary hover:text-foreground hover:bg-surface-2"
              )}
            >
              <Icon size={12} />
              {label}
            </Link>
          );
        })}
      </div>
      <span className="ms-auto text-[10px] text-text-dim hidden lg:inline flex-shrink-0">
        כלי פיתוח ובקרה — לא חלק מחוויית המוצר
      </span>
    </div>
  );
}
