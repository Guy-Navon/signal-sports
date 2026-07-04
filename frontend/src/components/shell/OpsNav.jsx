import React from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { getOpsNavItems } from "@/components/shell/navConfig";

// Console strip shown above ops pages — marks the dev/QA area as distinct
// from the product. The mono breadcrumb ("המערכת ⁄ קונסולה ⁄ current page")
// reads like a file path, reinforcing the instrument-panel feel.
export default function OpsNav({ isBackendMode }) {
  const location = useLocation();
  const opsItems = getOpsNavItems(isBackendMode);
  const currentLabel = opsItems.find((item) => item.path === location.pathname)?.label || "קונסולה";

  return (
    <div className="mb-6 bg-surface-1 border border-border rounded-[10px] px-3 py-2 flex items-center gap-3 overflow-x-auto">
      <span className="font-mono text-[11px] text-text-dim flex-shrink-0 tracking-tight">
        המערכת <span className="text-text-dim/50">⁄</span> קונסולה{" "}
        <span className="text-text-dim/50">⁄</span> <span className="text-signal-feed">{currentLabel}</span>
      </span>
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
