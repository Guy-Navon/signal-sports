import React from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { getMobileNavItems } from "@/components/shell/navConfig";

// Product: a floating glass pill, detached from the screen edge — the feed
// keeps the canvas, navigation becomes a light touch rather than a bar.
// Ops: the current edge-to-edge tab bar, unchanged (console shell redesign
// is a later PR).
export default function MobileNav({ area, isBackendMode }) {
  const location = useLocation();
  const items = getMobileNavItems(area, isBackendMode);

  if (area === "product") {
    return (
      <nav className="md:hidden fixed bottom-4 inset-x-4 z-50">
        <div className="surface-glass border border-border rounded-full shadow-lg flex items-center justify-between px-2 py-1.5">
          {items.map(({ path, label, icon: Icon }) => {
            const active = location.pathname === path;
            return (
              <Link
                key={path}
                to={path}
                className={cn(
                  "relative flex flex-col items-center gap-0.5 flex-1 py-1.5 rounded-full transition-colors",
                  active ? "text-signal-high" : "text-text-dim"
                )}
              >
                {active && (
                  <span className="absolute top-0.5 w-1 h-1 rounded-full bg-signal-high" />
                )}
                <Icon size={17} />
                <span className="text-[9px] leading-none">{label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    );
  }

  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 surface-glass border-t border-border z-50">
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
