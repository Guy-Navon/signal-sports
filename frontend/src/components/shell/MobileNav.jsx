import React from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { getMobileNavItems } from "@/components/shell/navConfig";

// Mobile navigation is an edge-to-edge newsroom dock. It deliberately avoids
// the floating-pill pattern so the full viewport width remains predictable.
export default function MobileNav({ area, isBackendMode }) {
  const location = useLocation();
  const items = getMobileNavItems(area, isBackendMode);

  if (area === "product") {
    return (
      <nav className="fixed inset-x-0 bottom-0 z-50 border-t border-foreground bg-foreground text-background md:hidden">
        <div className="mx-auto flex h-[4.25rem] max-w-lg items-stretch">
          {items.map(({ path, label, icon: Icon }) => {
            const active = location.pathname === path;
            return (
              <Link
                key={path}
                to={path}
                className={cn(
                  "relative flex flex-1 flex-col items-center justify-center gap-1 transition-colors",
                  active ? "bg-background text-foreground" : "text-background/55"
                )}
              >
                {active && <span className="absolute inset-x-0 top-0 h-[3px] bg-signal-push" />}
                <Icon size={18} />
                <span className="text-[10px] font-medium leading-none">{label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    );
  }

  return (
    <nav className="surface-glass fixed inset-x-0 bottom-0 z-50 border-t border-border md:hidden">
      <div className="flex">
        {items.map(({ path, label, icon: Icon }) => {
          const active = location.pathname === path;
          return (
            <Link
              key={path}
              to={path}
              className={cn(
                "flex-1 flex flex-col items-center py-2 gap-1 transition-colors",
                active ? "text-signal-high" : "text-text-dim"
              )}
            >
              <Icon size={18} />
              <span className="text-[10px]">{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
