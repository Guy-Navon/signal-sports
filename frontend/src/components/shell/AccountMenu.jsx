import React from "react";
import { Link } from "react-router-dom";
import { Check, LogOut, Settings2, Terminal, UserRound } from "lucide-react";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { useAuth } from "@/context/AuthContext";
import { useApp, SANDBOX_PROFILE_ID } from "@/context/AppContext";
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
import { accountInitial, accountMenuSections } from "@/components/shell/productShellModel";
import { GROUNDS } from "@/components/signal-ui/ground";
import { useGround } from "@/components/signal-ui/useGround";

function Indicator() {
  return (
    <span className="sg-ground-choice__indicator">
      <Menu.ItemIndicator><Check size={14} aria-hidden="true" /></Menu.ItemIndicator>
    </span>
  );
}

// The account menu of the consumer header (#491): "my account", the ground
// switch, an admin-only section (console entry, QA view-as, data mode) and sign
// out. The avatar trigger is the only account control in the chrome; the
// console entry and the view-as switcher live here instead of in the bar.
export default function AccountMenu({ isBackendMode, onOpenChange = undefined }) {
  const auth = useAuth();
  const { ground, setGround } = useGround();
  const { activeProfileId, setActiveProfileId, profileList } = useApp();
  const signedIn = Boolean(auth.authEnforced && auth.user);
  const view = { isBackendMode, authEnforced: auth.authEnforced, user: auth.user };
  // #54: a visitor who may not enter the console gets no entry to it. Admins
  // keep the view-as switcher (#53 follow-up); local/bypass always show it.
  const showConsoleEntry = canEnterOpsShell(view);
  const showSwitcher = productShowsProfileSwitcher(view);
  const sections = accountMenuSections({ signedIn, showConsoleEntry, showSwitcher });
  const consoleEntryPath = getOpsNavItems(isBackendMode)[0]?.path || "/sources";
  const initial = signedIn ? accountInitial(auth.user) : null;

  const blocks = {
    account: (
      <React.Fragment key="account">
        <DropdownMenuLabel dir="ltr" className="sg-menu-label truncate">
          {auth.user?.email || auth.user?.id}
        </DropdownMenuLabel>
        <DropdownMenuItem asChild className="gap-2 cursor-pointer">
          <Link to="/account">
            <Settings2 size={14} aria-hidden="true" />
            החשבון שלי
          </Link>
        </DropdownMenuItem>
      </React.Fragment>
    ),
    ground: (
      <React.Fragment key="ground">
        <DropdownMenuLabel className="sg-menu-label">רקע</DropdownMenuLabel>
        <Menu.RadioGroup value={ground} onValueChange={setGround} aria-label="רקע">
          {GROUNDS.map(({ id, label }) => (
            <Menu.RadioItem key={id} value={id} className="sg-ground-choice">
              <Indicator />
              {label}
            </Menu.RadioItem>
          ))}
        </Menu.RadioGroup>
      </React.Fragment>
    ),
    admin: (
      <React.Fragment key="admin">
        <DropdownMenuLabel className="sg-menu-label">ניהול</DropdownMenuLabel>
        {showConsoleEntry && (
          <DropdownMenuItem asChild className="gap-2 cursor-pointer">
            <Link to={consoleEntryPath}>
              <Terminal size={14} aria-hidden="true" />
              קונסולה
            </Link>
          </DropdownMenuItem>
        )}
        {showSwitcher && (
          <Menu.RadioGroup
            value={activeProfileId}
            onValueChange={setActiveProfileId}
            aria-label="צפייה בתור (QA)"
          >
            <DropdownMenuLabel className="sg-menu-label sg-menu-label--sub">צפייה בתור (QA)</DropdownMenuLabel>
            {profileList.map((profile) => (
              <Menu.RadioItem key={profile.id} value={profile.id} className="sg-ground-choice">
                <Indicator />
                <span className="flex-1">{profile.label}</span>
                {profile.id === SANDBOX_PROFILE_ID && <span className="sg-menu-badge">בדיקה</span>}
              </Menu.RadioItem>
            ))}
          </Menu.RadioGroup>
        )}
        <p className="sg-menu-note">מצב נתונים: {isBackendMode ? "שרת" : "מקומי"}</p>
      </React.Fragment>
    ),
    signout: (
      <DropdownMenuItem key="signout" onSelect={() => auth.logout()} className="gap-2 cursor-pointer">
        <LogOut size={14} aria-hidden="true" />
        התנתקות
      </DropdownMenuItem>
    ),
  };

  return (
    <DropdownMenu dir="rtl" onOpenChange={onOpenChange}>
      <DropdownMenuTrigger aria-label="החשבון" className="sg-avatar-btn">
        <span className="sg-avatar-btn__face">
          {initial ?? <UserRound size={16} aria-hidden="true" />}
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="sg-account-menu">
        {sections.flatMap((id, index) => [
          index > 0 ? <DropdownMenuSeparator key={`sep-${id}`} /> : null,
          blocks[id],
        ])}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
