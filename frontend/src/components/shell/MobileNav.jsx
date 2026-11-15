import React from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { getMobileNavItems } from "@/components/shell/navConfig";

// The Ops console's phone tab bar: edge to edge, console items plus a way back
// to the feed. The consumer product has its own dock since #463 (ProductDock).
export default function MobileNav({ isBackendMode }) {
  const location = useLocation();
  const items = getMobileNavItems("ops", isBackendMode);

  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 pb-[env(safe-area-inset-bottom)] surface-glass border-t border-border z-50">
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
