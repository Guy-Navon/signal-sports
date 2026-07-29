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
      <nav className="orbit-mobile-nav md:hidden fixed inset-x-3 z-50">
        <div className="orbit-mobile-dock flex items-center justify-between px-1.5 py-1.5">
          {items.map(({ path, label, icon: Icon }) => {
            const active = location.pathname === path;
            return (
              <Link
                key={path}
                to={path}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "orbit-mobile-link relative flex flex-col items-center gap-0.5 flex-1 py-2 rounded-full transition-colors",
                  active ? "text-signal-high" : "text-text-secondary"
                )}
              >
                {active && (
                  <span className="orbit-mobile-link__active absolute inset-0 rounded-full" />
                )}
                <Icon size={17} className="relative z-10" />
                <span className="relative z-10 text-[10px] leading-none">{label}</span>
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
              aria-current={active ? "page" : undefined}
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
