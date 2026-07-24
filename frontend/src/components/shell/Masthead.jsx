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
        "relative flex h-16 items-center px-3 text-[13px] font-medium transition-colors",
        active
          ? "bg-background text-foreground"
          : "text-background/65 hover:bg-background/10 hover:text-background"
      )}
    >
      {label}
      {active && <span className="absolute inset-x-0 bottom-0 h-[3px] bg-signal-push" />}
    </Link>
  );
}

function AccountMenu({ inverted = false }) {
  const auth = useAuth();
  if (!auth.authEnforced || !auth.user) return null;

  return (
    <DropdownMenu dir="rtl">
      <DropdownMenuTrigger
        aria-label="חשבון"
        className={cn(
          "inline-flex h-9 w-9 items-center justify-center border transition-colors",
          inverted
            ? "border-background/20 text-background/70 hover:border-background/55 hover:text-background"
            : "border-border text-text-secondary hover:border-foreground/40 hover:text-foreground"
        )}
      >
        <UserRound size={15} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[210px]">
        <DropdownMenuLabel dir="ltr" className="truncate font-normal text-text-secondary">
          {auth.user.email || auth.user.id}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild className="cursor-pointer gap-2">
          <Link to="/account">
            <Settings2 size={14} />
            החשבון שלי
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => auth.logout()} className="cursor-pointer gap-2">
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
  const consumerView = {
    isBackendMode,
    authEnforced: auth.authEnforced,
    user: auth.user,
  };
  const showSwitcher = area === "ops" || productShowsProfileSwitcher(consumerView);
  const showConsoleEntry = canEnterOpsShell(consumerView);
  const opsItems = getOpsNavItems(isBackendMode);
  const consoleEntryPath = opsItems[0]?.path || "/sources";
  const product = area === "product";

  return (
    <header
      className={cn(
        "sticky top-0 z-50 border-b transition-shadow duration-300",
        product
          ? "border-foreground bg-foreground text-background"
          : "surface-glass border-border",
        scrolled && "shadow-[0_10px_30px_hsl(var(--foreground)/0.08)]"
      )}
    >
      <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
        <div className="flex min-w-0 items-center gap-3 md:gap-6">
          <Link
            to="/"
            className={cn(
              "flex flex-shrink-0 items-center gap-2",
              product ? "text-background" : "text-foreground"
            )}
          >
            <SignalMark />
            <span className="flex items-baseline gap-2">
              <span className="font-display text-xl font-bold leading-none tracking-tight">סיגנל</span>
              <span className="hidden font-mono text-[8px] font-bold tracking-[0.2em] opacity-50 sm:inline">
                SPORTS DESK
              </span>
            </span>
          </Link>

          {product && (
            <nav className="hidden h-16 items-center border-s border-background/15 ps-3 md:flex">
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

          {!product && (
            <Link
              to="/"
              className="hidden items-center gap-1.5 text-sm text-text-secondary transition-colors hover:text-foreground md:inline-flex"
            >
              <Rss size={13} />
              חזרה למוצר
            </Link>
          )}
        </div>

        <div className="flex flex-shrink-0 items-center gap-2">
          {isBackendMode && isLoading && (
            <RefreshCw
              size={12}
              className={cn("animate-spin", product ? "text-background/60" : "text-signal-high")}
            />
          )}
          <DataModeBadge
            isBackendMode={isBackendMode}
            className={cn(product && "hidden text-background/60 sm:inline-flex")}
          />
          {showSwitcher && (
            <div className="flex items-center gap-1.5">
              {auth.authEnforced && auth.user && (
                <span
                  className={cn(
                    "hidden font-mono text-[9px] uppercase tracking-wider md:inline",
                    product ? "text-background/45" : "text-text-dim"
                  )}
                >
                  QA
                </span>
              )}
              <ProfileSwitcher inverted={product} />
            </div>
          )}
          <AccountMenu inverted={product} />
          {product && showConsoleEntry && (
            <Link
              to={consoleEntryPath}
              title="קונסולה"
              aria-label="כניסה לקונסולה"
              className="hidden h-9 w-9 items-center justify-center border border-background/20 text-background/60 transition-colors hover:border-background/55 hover:text-background md:inline-flex"
            >
              <Terminal size={15} />
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
