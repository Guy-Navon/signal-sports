import React from "react";
import { Outlet, useLocation } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { useApp } from "@/context/AppContext";
import Masthead from "@/components/shell/Masthead";
import MobileNav from "@/components/shell/MobileNav";
import OpsGrid from "@/components/shell/OpsGrid";
import ProductNav from "@/components/shell/ProductNav";
import OpsNav from "@/components/shell/OpsNav";
import ProductShell from "@/components/shell/ProductShell";
import ErrorState from "@/components/shared/ErrorState";
import { connectionErrorStrip } from "@/components/feed/feedLoadModel";

// Two worlds, one entry point. The consumer product renders the new shell
// (#463, ProductShell). The Ops console keeps its console rail, flat
// instrument-panel backdrop and existing look, unchanged by milestone 15.
export default function AppShell({ area = "product" }) {
  if (area === "product") return <ProductShell />;
  return <OpsShell />;
}

function OpsShell() {
  const { isBackendMode, isLoading, apiError, refreshFeed } = useApp();
  const location = useLocation();
  const reduce = useReducedMotion();

  return (
    <div className="min-h-screen flex flex-col relative">
      <OpsGrid />

      <Masthead isBackendMode={isBackendMode} isLoading={isLoading} />

      {isBackendMode && apiError && (
        <ErrorState
          variant="strip"
          {...connectionErrorStrip({ area: "ops", message: apiError })}
          onRetry={refreshFeed}
        />
      )}

      <div className="flex-1 flex w-full max-w-screen-2xl mx-auto">
        <ProductNav isBackendMode={isBackendMode} />
        <main className="flex-1 min-w-0">
          <div className="mx-auto w-full max-w-7xl px-4 py-6 pb-24 md:pb-10">
            <OpsNav isBackendMode={isBackendMode} />
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
          </div>
        </main>
      </div>

      <MobileNav isBackendMode={isBackendMode} />
    </div>
  );
}
