import React from "react";
import { Link } from "react-router-dom";
import { RefreshCw, Rss, LogOut, Settings2, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";
import SignalMark from "@/components/shell/SignalMark";
import DataModeBadge from "@/components/shell/DataModeBadge";
import ProfileSwitcher from "@/components/shell/ProfileSwitcher";
import { useAuth } from "@/context/AuthContext";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useScrolled } from "@/components/shell/useScrolled";

// The Ops console masthead (the consumer product has its own shell since
// #463, ProductShell): wordmark, a "back to the product" link, the QA view-as
// switcher, data mode and the account menu. Starts transparent over the
// console backdrop and gains glass + a hairline once the page scrolls.
// Account menu (User Platform PR 3, #51): rendered only under real
// enforcement with a signed-in user.
function AccountMenu() {
  const auth = useAuth();
  if (!auth.authEnforced || !auth.user) return null;
  const label = auth.user.email || auth.user.id;
  return (
    <DropdownMenu dir="rtl">
      <DropdownMenuTrigger
        aria-label="חשבון"
        className="inline-flex items-center justify-center w-8 h-8 max-md:w-11 max-md:h-11 rounded-lg text-text-dim hover:text-foreground hover:bg-surface-2 transition-colors"
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

export default function Masthead({ isBackendMode, isLoading }) {
  const scrolled = useScrolled();
  const auth = useAuth();

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
            <span className="orbit-wordmark font-display font-bold text-foreground text-[1.05rem] tracking-tight">
              <span>סיגנל</span>
            </span>
          </Link>

          <Link
            to="/"
            className="hidden md:inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-foreground transition-colors"
          >
            <Rss size={13} />
            חזרה למוצר
          </Link>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {isBackendMode && isLoading && (
            <RefreshCw size={12} className="text-signal-high animate-spin" />
          )}
          <DataModeBadge isBackendMode={isBackendMode} />
          <div className="flex items-center gap-1.5">
            {auth.authEnforced && auth.user && (
              <span className="hidden md:inline text-[10px] font-mono uppercase tracking-wider text-text-dim">
                QA view-as
              </span>
            )}
            <ProfileSwitcher />
          </div>
          <AccountMenu />
        </div>
      </div>
    </header>
  );
}
