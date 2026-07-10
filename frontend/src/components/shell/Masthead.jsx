import React from "react";
import { Link, useLocation } from "react-router-dom";
import { RefreshCw, Terminal, Rss, LogOut, Settings2, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";
import SignalMark from "@/components/shell/SignalMark";
import DataModeBadge from "@/components/shell/DataModeBadge";
import ProfileSwitcher from "@/components/shell/ProfileSwitcher";
import { useAuth } from "@/context/AuthContext";
import { canEnterOpsShell, productShowsProfileSwitcher } from "@/context/dataRouting";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
// Account menu (User Platform PR 3, #51): rendered only under real
// enforcement with a signed-in user — local/bypass modes keep the masthead
// pixel-identical to the pre-auth UI. The account page itself arrives in PR 7.
function AccountMenu() {
  const auth = useAuth();
  if (!auth.authEnforced || !auth.user) return null;
  const label = auth.user.email || auth.user.id;
  return (
    <DropdownMenu dir="rtl">
      <DropdownMenuTrigger
        aria-label="חשבון"
        className="inline-flex items-center justify-center w-8 h-8 rounded-lg text-text-dim hover:text-foreground hover:bg-surface-2 transition-colors"
      >
        <UserRound size={15} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[200px]">
        <DropdownMenuLabel dir="ltr" className="font-normal text-text-secondary truncate">
          {label}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild className="gap-2 cursor-pointer">
          <Link to="/account">
            <Settings2 size={14} />
            החשבון שלי
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => auth.logout()} className="gap-2 cursor-pointer">
          <LogOut size={14} />
          התנתקות
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default function Masthead({ area, isBackendMode, isLoading }) {
  const location = useLocation();
  const scrolled = useScrolled();
  const auth = useAuth();
  // PR 5 (#53): under a consumer session the ProfileSwitcher leaves the
  // product masthead (the session IS the product identity) and remains on the
  // ops console as the admin QA view-as control. Local/bypass: today's UI.
  const consumerView = {
    isBackendMode,
    authEnforced: auth.authEnforced,
    user: auth.user,
  };
  const showSwitcher =
    area === "ops" || productShowsProfileSwitcher(consumerView);
  // #54 review (MEDIUM): consumer role=user must not see a console entry.
  const showConsoleEntry = canEnterOpsShell(consumerView);
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
          {showSwitcher && (
            <div className="flex items-center gap-1.5">
              {area === "ops" && auth.authEnforced && auth.user && (
                <span className="hidden md:inline text-[10px] font-mono uppercase tracking-wider text-text-dim">
                  QA view-as
                </span>
              )}
              <ProfileSwitcher />
            </div>
          )}
          <AccountMenu />
          {area === "product" && showConsoleEntry && (
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
