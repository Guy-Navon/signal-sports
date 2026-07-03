import React from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { PRODUCT_NAV_ITEMS, getOpsNavItems } from "@/components/shell/navConfig";

function NavItem({ path, label, icon: Icon, active, muted }) {
  return (
    <Link
      to={path}
      className={cn(
        "relative flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
        active
          ? "bg-signal-high/10 text-signal-high font-medium"
          : muted
            ? "text-text-dim hover:text-text-secondary hover:bg-surface-2"
            : "text-text-secondary hover:text-foreground hover:bg-surface-2"
      )}
    >
      {active && (
        <span className="absolute inline-block start-0 top-1/2 -translate-y-1/2 w-0.5 h-4 rounded-full bg-signal-high" />
      )}
      <Icon size={15} className="flex-shrink-0" />
      {label}
    </Link>
  );
}

function GroupLabel({ children }) {
  return <p className="px-3 pt-4 pb-1 text-[10px] font-medium text-text-dim">{children}</p>;
}

// Desktop navigation rail — product group on top, ops console group below a separator.
export default function ProductNav({ isBackendMode }) {
  const location = useLocation();
  const opsItems = getOpsNavItems(isBackendMode);

  return (
    <nav className="hidden md:block w-48 flex-shrink-0 pt-6 pe-2">
      <div className="sticky top-20 space-y-0.5">
        <GroupLabel>מוצר</GroupLabel>
        {PRODUCT_NAV_ITEMS.map((item) => (
          <NavItem key={item.path} {...item} active={location.pathname === item.path} />
        ))}
        <div className="mx-3 my-3 border-t border-border" />
        <GroupLabel>קונסולה</GroupLabel>
        {opsItems.map((item) => (
          <NavItem key={item.path} {...item} active={location.pathname === item.path} muted />
        ))}
      </div>
    </nav>
  );
}
