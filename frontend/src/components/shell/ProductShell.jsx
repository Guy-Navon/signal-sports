import React, { useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useApp } from "@/context/AppContext";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import { GroundProvider, useGround } from "@/components/signal-ui/useGround";
import ErrorState from "@/components/shared/ErrorState";
import { connectionErrorStrip } from "@/components/feed/feedLoadModel";
import ProductTopBar from "@/components/shell/ProductTopBar";
import ProductDock from "@/components/shell/ProductDock";
import { MastheadSlotContext } from "@/components/shell/MastheadSlot";
import { pageSurface } from "@/components/shell/productShellModel";
import "@/components/signal-ui/signal-ui.css";
import "@/components/shell/shell.css";

// The consumer product shell (#463, Part B §B5–B6): navy top bar, centred
// wordmark masthead with a page slot beneath it, the page, and a bottom dock
// on phones. The chrome carries the `.signal-ui` scope (white ground by
// default). The page body carries a scope chosen per route: pages not yet
// rebuilt keep `.orbit-product`, so their Orbit tokens still resolve exactly
// as before; rebuilt pages get `.signal-ui`. See productShellModel.pageSurface.
export default function ProductShell() {
  return <GroundProvider><ProductShellContent /></GroundProvider>;
}

function ProductShellContent() {
  const { ground } = useGround();
  const { isBackendMode, isLoading, apiError, refreshFeed } = useApp();
  const location = useLocation();
  const reduce = useReducedMotion();
  // Callback-ref state, so pages re-render with the node once it exists.
  const [slotNode, setSlotNode] = useState(null);
  const surface = pageSurface(location.pathname);

  return (
    <div className="sg-shell">
      <a href="#sg-main" className="signal-ui sg-skip" data-ground={ground}>
        דילוג לתוכן
      </a>

      <header className="signal-ui sg-chrome" data-ground={ground}>
        <ProductTopBar isBackendMode={isBackendMode} isLoading={isLoading} />
        <div className="sg-gutter">
          <div className="sg-container sg-masthead">
            <Link to="/" className="sg-masthead__brand" aria-label="סיגנל, לפיד">
              <SignalWordmark />
            </Link>
            <div ref={setSlotNode} className="sg-masthead__slot" />
          </div>
        </div>
      </header>

      <main
        id="sg-main"
        tabIndex={-1}
        data-ground={surface === "signal" ? ground : undefined}
        className={cn(
          "sg-body",
          surface === "orbit" ? "orbit-product sg-body--orbit" : "signal-ui sg-body--signal"
        )}
      >
        {isBackendMode && apiError && (
          <ErrorState
            variant="strip"
            {...connectionErrorStrip({ area: "product", message: apiError })}
            onRetry={refreshFeed}
          />
        )}
        <div
          className={
            surface === "orbit"
              ? "w-full max-w-screen-2xl mx-auto px-4 pt-5 pb-28 md:px-5 md:pt-6 md:pb-12"
              : "w-full"
          }
        >
          <MastheadSlotContext.Provider value={slotNode}>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={location.pathname}
                initial={reduce ? { opacity: 0 } : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
                transition={{ duration: reduce ? 0.12 : 0.28, ease: [0.22, 1, 0.36, 1] }}
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          </MastheadSlotContext.Provider>
        </div>
      </main>

      <ProductDock isBackendMode={isBackendMode} />
    </div>
  );
}
