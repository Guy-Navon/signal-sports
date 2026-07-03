import React from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { RefreshCw, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { useApp } from "@/context/AppContext";
import ProfileSwitcher from "@/components/shell/ProfileSwitcher";
import DataModeBadge from "@/components/shell/DataModeBadge";
import OpsNav from "@/components/shell/OpsNav";
import ProductNav from "@/components/shell/ProductNav";
import ErrorState from "@/components/shared/ErrorState";
import { getMobileNavItems } from "@/components/shell/navConfig";

function MobileTabBar({ area, isBackendMode }) {
  const location = useLocation();
  const items = getMobileNavItems(area, isBackendMode);

  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 surface-glass border-t border-border z-50">
      <div className="flex">
        {items.map(({ path, label, icon: Icon }) => {
          const active = location.pathname === path;
          return (
            <Link
              key={path}
              to={path}
              className={cn(
                "flex-1 flex flex-col items-center py-2 gap-1 transition-colors",
                active ? "text-signal-high" : "text-text-dim"
              )}
            >
              <Icon size={18} />
              <span className="text-[10px]">{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

export default function AppShell({ area = "product" }) {
  const { isBackendMode, isLoading, apiError, refreshFeed } = useApp();

  return (
    <div className="min-h-screen flex flex-col">
      <header className="surface-glass border-b border-border sticky top-0 z-50">
        <div className="max-w-screen-2xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-signal-high to-signal-ai flex items-center justify-center elevation-1">
                <Zap size={14} className="text-background" fill="currentColor" />
              </div>
              <span className="font-bold text-foreground text-base tracking-tight">
                Signal Sports
              </span>
            </Link>
            <DataModeBadge isBackendMode={isBackendMode} />
            {isBackendMode && isLoading && (
              <RefreshCw size={12} className="text-signal-high animate-spin" />
            )}
          </div>
          <ProfileSwitcher />
        </div>
      </header>

      {isBackendMode && apiError && (
        <ErrorState
          variant="strip"
          title="שגיאה בחיבור לשרת"
          message={apiError}
          hint="שרת צריך לרוץ על http://127.0.0.1:8000"
          onRetry={refreshFeed}
        />
      )}

      <div className="flex-1 flex w-full max-w-screen-2xl mx-auto">
        <ProductNav isBackendMode={isBackendMode} />
        <main className="flex-1 min-w-0">
          <div className="mx-auto w-full max-w-7xl px-4 py-6 pb-24 md:pb-10">
            {area === "ops" && <OpsNav isBackendMode={isBackendMode} />}
            <Outlet />
          </div>
        </main>
      </div>

      <MobileTabBar area={area} isBackendMode={isBackendMode} />
    </div>
  );
}
