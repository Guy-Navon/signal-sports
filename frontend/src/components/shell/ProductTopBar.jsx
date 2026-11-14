import React from "react";
import { Link, useLocation } from "react-router-dom";
import { Check, LogOut, RefreshCw, Settings2, Terminal, UserRound } from "lucide-react";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
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
import { getOpsNavItems } from "@/components/shell/navConfig";
import { consumerNavItems } from "@/components/shell/productShellModel";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { GROUNDS } from "@/components/signal-ui/ground";
import { useGround } from "@/components/signal-ui/useGround";

// The ground is a device preference, available in local/bypass mode too.
// Account links and sign-out still require a real signed-in account.
function AccountEntry() {
  const auth = useAuth();
  const { ground, setGround } = useGround();
  const signedIn = auth.authEnforced && auth.user;
  const label = signedIn ? auth.user.email || auth.user.id : null;
  return (
    <DropdownMenu dir="rtl">
      <DropdownMenuTrigger aria-label="החשבון" className="sg-topbar__control">
        <UserRound size={15} aria-hidden="true" />
        <span className="sg-topbar__wide">החשבון</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {signedIn && (
          <>
            <DropdownMenuLabel dir="ltr" className="sg-menu-label truncate">
              {label}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild className="gap-2 cursor-pointer">
              <Link to="/account">
                <Settings2 size={14} />
                החשבון שלי
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </>
        )}
        <DropdownMenuLabel className="sg-menu-label">רקע</DropdownMenuLabel>
        <Menu.RadioGroup value={ground} onValueChange={setGround} aria-label="רקע">
          {GROUNDS.map(({ id, label: groundLabel }) => (
            <Menu.RadioItem key={id} value={id} className="sg-ground-choice">
              <span className="sg-ground-choice__indicator">
                <Menu.ItemIndicator><Check size={14} aria-hidden="true" /></Menu.ItemIndicator>
              </span>
              {groundLabel}
            </Menu.RadioItem>
          ))}
        </Menu.RadioGroup>
        {signedIn && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => auth.logout()} className="gap-2 cursor-pointer">
              <LogOut size={14} />
              התנתקות
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// The navy top bar of the consumer product (Part B §B6): navigation at the
// inline start, the account at the inline end. On a phone the navigation
// moves to the dock (ProductDock) and the bar keeps only the end group.
export default function ProductTopBar({ isBackendMode, isLoading }) {
  const location = useLocation();
  const auth = useAuth();
  const consumerView = { isBackendMode, authEnforced: auth.authEnforced, user: auth.user };
  // Admins keep the view-as switcher on the product page (#53 follow-up);
  // local/bypass always show it. A role=user session never does.
  const showSwitcher = productShowsProfileSwitcher(consumerView);
  // #54: a visitor who may not enter the console gets no entry to it.
  const showConsoleEntry = canEnterOpsShell(consumerView);
  const consoleEntryPath = getOpsNavItems(isBackendMode)[0]?.path || "/sources";

  return (
    <div className="sg-topbar sg-gutter">
      <div className="sg-container sg-topbar__inner">
        {/* Phone only: the bar carries the wordmark so the chrome stays one
            compact row above the page (the masthead block hides there). */}
        <Link to="/" className="sg-topbar__brand" aria-label="סיגנל, לפיד">
          <SignalWordmark />
        </Link>
        <nav aria-label="ניווט ראשי" className="sg-topbar__nav">
          {consumerNavItems().map((item) => (
            <Link
              key={item.path}
              to={item.path}
              aria-current={location.pathname === item.path ? "page" : undefined}
              className="sg-topbar__link"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="sg-topbar__end">
          {isBackendMode && isLoading && (
            <RefreshCw size={12} className="animate-spin" aria-hidden="true" />
          )}
          <DataModeBadge isBackendMode={isBackendMode} />
          {showSwitcher && (
            <div className="sg-topbar__viewas">
              {auth.authEnforced && auth.user && (
                <span className="sg-topbar__wide sg-topbar__note">QA view-as</span>
              )}
              <ProfileSwitcher variant="topbar" />
            </div>
          )}
          {showConsoleEntry && (
            <Link
              to={consoleEntryPath}
              title="קונסולה"
              aria-label="כניסה לקונסולה"
              className="sg-topbar__control sg-topbar__wide-flex"
            >
              <Terminal size={15} aria-hidden="true" />
            </Link>
          )}
          <AccountEntry />
        </div>
      </div>
    </div>
  );
}
