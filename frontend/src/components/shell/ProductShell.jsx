import React, { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { useApp } from "@/context/AppContext";
import { GroundProvider, useGround } from "@/components/signal-ui/useGround";
import ErrorState from "@/components/shared/ErrorState";
import { connectionErrorStrip } from "@/components/feed/feedLoadModel";
import ProductHeader from "@/components/shell/ProductHeader";
import { MastheadSlotContext } from "@/components/shell/MastheadSlot";
import "@/components/signal-ui/signal-ui.css";
import "@/components/shell/shell.css";

// The consumer product shell (#463, navigation #491, Part B §B5–B6): the navy
// header (expanded masthead + slim bar on scroll, ProductHeader), the page slot
// directly beneath it (outside the sticky bar), then the page. No bottom dock.
// All consumer pages carry `.signal-ui` (white ground by default).
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
        data-ground={ground}
        className="sg-body signal-ui sg-body--signal"
      >
        {isBackendMode && apiError && (
          <ErrorState
            variant="strip"
            {...connectionErrorStrip({ area: "product", message: apiError })}
            onRetry={refreshFeed}
          />
        )}
        <div className="w-full">
          <MastheadSlotContext.Provider value={slotNode}>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={location.pathname.startsWith("/preferences") ? "/preferences" : location.pathname}
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
