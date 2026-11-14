import React, { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useApp } from "@/context/AppContext";
import { GroundProvider, useGround } from "@/components/signal-ui/useGround";
import ErrorState from "@/components/shared/ErrorState";
import { connectionErrorStrip } from "@/components/feed/feedLoadModel";
import ProductHeader from "@/components/shell/ProductHeader";
import { MastheadSlotContext } from "@/components/shell/MastheadSlot";
import { pageSurface } from "@/components/shell/productShellModel";
import "@/components/signal-ui/signal-ui.css";
import "@/components/shell/shell.css";

// The consumer product shell (#463, navigation #491, Part B §B5–B6): the navy
// header (expanded masthead + slim bar on scroll, ProductHeader), the page slot
// directly beneath it (outside the sticky bar), then the page. No bottom dock.
// The chrome carries the `.signal-ui` scope (white ground by default). The page body carries a scope chosen per route: pages not yet
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

      <ProductHeader ground={ground} isBackendMode={isBackendMode} isLoading={isLoading} />

      {/* Page content under the header (the feed's summary line and league
          pills, MastheadSlot). In the page flow, never inside the sticky bar. */}
      <div className="signal-ui sg-gutter sg-slotband" data-ground={ground}>
        <div ref={setSlotNode} className="sg-container sg-masthead__slot" />
      </div>

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
    </div>
  );
}
