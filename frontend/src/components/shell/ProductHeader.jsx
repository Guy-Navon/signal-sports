import React, { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import AccountMenu from "@/components/shell/AccountMenu";
import { consumerIcon } from "@/components/shell/navIcons";
import { consumerNavItems, mastheadDate } from "@/components/shell/productShellModel";
import { useCollapsedBar } from "@/components/shell/useCollapsedBar";

// The consumer header (#491, Part B §B6), navy in both states:
//  - the expanded masthead in normal page flow: large centred logo, the date,
//    the tabs with words, the account at the inline end. It scrolls away.
//  - a slim fixed bar that fades and slides in once the masthead's tabs have
//    left the top (useCollapsedBar): small logo at the inline start, the tabs,
//    the account. On a phone each tab there is an icon over a small label.
// The bar is out of flow, so showing or hiding it never moves the content.

function NavTabs({ label, compact = false, navRef = undefined }) {
  const location = useLocation();
  return (
    <nav ref={navRef} aria-label={label} className={compact ? "sg-tabs sg-tabs--compact" : "sg-tabs"}>
      {consumerNavItems().map((item) => {
        const Icon = consumerIcon(item);
        return (
          <Link
            key={item.path}
            to={item.path}
            aria-current={location.pathname === item.path || (item.path === "/preferences" && location.pathname.startsWith("/preferences/")) ? "page" : undefined}
            className="sg-tab"
          >
            {compact && Icon && <Icon size={20} strokeWidth={2} aria-hidden="true" className="sg-tab__icon" />}
            <span className="sg-tab__label">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function useToday() {
  const [today, setToday] = useState(() => mastheadDate(new Date()));
  useEffect(() => {
    const id = setInterval(() => setToday(mastheadDate(new Date())), 60_000);
    return () => clearInterval(id);
  }, []);
  return today;
}

// A thin line on the header's bottom edge while the feed loads; it replaces the
// spinner the old top bar carried. Decorative: the pages announce their own
// loading states.
function Progress({ on }) {
  return on ? <span className="sg-progress" aria-hidden="true" /> : null;
}

export default function ProductHeader({ ground, isBackendMode, isLoading }) {
  const tabsRef = useRef(null);
  const barRef = useRef(null);
  const { shown, onMenuOpenChange } = useCollapsedBar(tabsRef, barRef);
  const today = useToday();
  const loading = Boolean(isBackendMode && isLoading);

  return (
    <>
      <header className="signal-ui sg-on-top sg-head" data-ground={ground}>
        <div className="sg-gutter">
          <div className="sg-container sg-head__inner">
            <Link to="/" className="sg-head__brand" aria-label="סיגנל, לפיד">
              <SignalWordmark />
            </Link>
            <p className="sg-head__date">{today}</p>
            <NavTabs navRef={tabsRef} label="ניווט ראשי" />
            <div className="sg-head__end">
              <AccountMenu isBackendMode={isBackendMode} />
            </div>
          </div>
        </div>
        <Progress on={loading} />
      </header>

      <div
        ref={barRef}
        className="signal-ui sg-on-top sg-bar"
        data-ground={ground}
        data-shown={shown ? "" : undefined}
      >
        <div className="sg-bar__gutter">
          <div className="sg-container sg-bar__inner">
            <Link to="/" className="sg-bar__brand" aria-label="סיגנל, לפיד">
              <SignalWordmark />
            </Link>
            <NavTabs compact label="ניווט ראשי, שורה מקוצרת" />
            <div className="sg-bar__end">
              <AccountMenu isBackendMode={isBackendMode} onOpenChange={onMenuOpenChange} />
            </div>
          </div>
        </div>
        <Progress on={loading} />
      </div>
    </>
  );
}
