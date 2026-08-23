import React from "react";
import { Outlet, useLocation } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { useApp } from "@/context/AppContext";
import Masthead from "@/components/shell/Masthead";
import MobileNav from "@/components/shell/MobileNav";
import Atmosphere from "@/components/shell/Atmosphere";
import OpsGrid from "@/components/shell/OpsGrid";
import ProductNav from "@/components/shell/ProductNav";
import OpsNav from "@/components/shell/OpsNav";
import ErrorState from "@/components/shared/ErrorState";

// Product routes live inside Orbit's ambient intelligence canvas — no sidebar;
// the masthead carries navigation and the feed gets the full width. Ops keeps
// its console rail and flat instrument-panel backdrop: two worlds, one shell.
export default function AppShell({ area = "product" }) {
  const { isBackendMode, isLoading, apiError, refreshFeed } = useApp();
  const location = useLocation();
  const reduce = useReducedMotion();

  return (
    <div
      className={
        area === "product"
          ? "orbit-product min-h-screen flex flex-col relative"
          : "min-h-screen flex flex-col relative"
      }
    >
      {area === "product" ? <Atmosphere /> : <OpsGrid />}

      <Masthead area={area} isBackendMode={isBackendMode} isLoading={isLoading} />

      {isBackendMode && apiError && (
        <ErrorState
          variant="strip"
          title="שגיאה בחיבור לשרת"
          message={apiError}
          hint="ודא ששרת ה-API רץ (uvicorn, פורט 8000)"
          onRetry={refreshFeed}
        />
      )}

      <div className="flex-1 flex w-full max-w-screen-2xl mx-auto">
        {area === "ops" && <ProductNav isBackendMode={isBackendMode} />}
        <main className="flex-1 min-w-0">
          <div
            className={
              area === "product"
                ? "w-full px-4 pt-5 pb-28 md:px-5 md:pt-6 md:pb-12"
                : "mx-auto w-full max-w-7xl px-4 py-6 pb-24 md:pb-10"
            }
          >
            {area === "ops" && <OpsNav isBackendMode={isBackendMode} />}
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

      <MobileNav area={area} isBackendMode={isBackendMode} />
    </div>
  );
}
