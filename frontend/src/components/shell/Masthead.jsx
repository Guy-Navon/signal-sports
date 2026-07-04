import React from "react";
import { Link, useLocation } from "react-router-dom";
import { RefreshCw, Terminal, Rss } from "lucide-react";
import { cn } from "@/lib/utils";
import SignalMark from "@/components/shell/SignalMark";
import DataModeBadge from "@/components/shell/DataModeBadge";
import ProfileSwitcher from "@/components/shell/ProfileSwitcher";
import { useScrolled } from "@/components/shell/useScrolled";
import { PRODUCT_NAV_ITEMS, getOpsNavItems } from "@/components/shell/navConfig";

function InlineNavLink({ path, label, active }) {
  return (
    <Link
      to={path}
      className={cn(
        "relative px-1 py-1 text-sm transition-colors",
        active ? "text-foreground font-medium" : "text-text-secondary hover:text-foreground"
      )}
    >
      {label}
      {active && (
        <span className="absolute -bottom-[13px] inset-x-0 h-0.5 rounded-full bg-signal-high" />
      )}
    </Link>
  );
}

// The masthead: wordmark, inline product navigation, profile + data-mode +
// console entry. Starts transparent over the atmosphere and gains glass +
// a hairline only once the page scrolls — premium without dominating the
// feed beneath it. Ops routes get the same masthead minus the inline product
// links (they navigate via the OpsNav rail instead) plus a "back to feed" link.
export default function Masthead({ area, isBackendMode, isLoading }) {
  const location = useLocation();
  const scrolled = useScrolled();
  const opsItems = getOpsNavItems(isBackendMode);
  const consoleEntryPath = opsItems[0]?.path || "/sources";

  return (
    <header
      className={cn(
        "sticky top-0 z-50 transition-colors duration-300",
        scrolled ? "surface-glass border-b border-border" : "bg-transparent border-b border-transparent"
      )}
    >
      <div className="max-w-screen-2xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
        <div className="flex items-center gap-6 min-w-0">
          <Link to="/" className="flex items-center gap-2 flex-shrink-0">
            <SignalMark />
            <span className="font-display font-bold text-foreground text-[1.05rem] tracking-tight">
              סיגנל
            </span>
          </Link>

          {area === "product" && (
            <nav className="hidden md:flex items-center gap-5">
              {PRODUCT_NAV_ITEMS.map((item) => (
                <InlineNavLink
                  key={item.path}
                  path={item.path}
                  label={item.label}
                  active={location.pathname === item.path}
                />
              ))}
            </nav>
          )}

          {area === "ops" && (
            <Link
              to="/"
              className="hidden md:inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-foreground transition-colors"
            >
              <Rss size={13} />
              חזרה למוצר
            </Link>
          )}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {isBackendMode && isLoading && (
            <RefreshCw size={12} className="text-signal-high animate-spin" />
          )}
          <DataModeBadge isBackendMode={isBackendMode} />
          <ProfileSwitcher />
          {area === "product" && (
            <Link
              to={consoleEntryPath}
              title="קונסולה"
              aria-label="כניסה לקונסולה"
              className="hidden md:inline-flex items-center justify-center w-8 h-8 rounded-lg text-text-dim hover:text-foreground hover:bg-surface-2 transition-colors"
            >
              <Terminal size={15} />
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
