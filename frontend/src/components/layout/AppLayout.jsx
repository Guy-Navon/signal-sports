import React from "react";
import { Link, useLocation } from "react-router-dom";
import { Rss, Settings, Sliders, Database, BarChart2, Bug, RefreshCw } from "lucide-react";
import ProfileSwitcher from "@/components/feed/ProfileSwitcher";
import { Outlet } from "react-router-dom";
import { useApp } from "@/context/AppContext";

const navItems = [
  { path: "/", label: "פיד אישי", icon: Rss },
  { path: "/preferences", label: "העדפות", icon: Settings },
  { path: "/calibration", label: "כיוונון", icon: Sliders },
  { path: "/sources", label: "מקורות", icon: Database },
  { path: "/results", label: "תוצאות", icon: BarChart2 },
  { path: "/debug", label: "דיבאג", icon: Bug }
];

export default function AppLayout() {
  const location = useLocation();
  const { isBackendMode, isLoading, apiError, refreshFeed } = useApp();

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col" dir="rtl">
      {/* Top Header */}
      <header className="border-b border-gray-800 bg-gray-950/95 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-md bg-emerald-500 flex items-center justify-center">
              <span className="text-gray-950 font-black text-xs">S</span>
            </div>
            <span className="font-bold text-white text-base tracking-tight">Signal Sports</span>
            {/* Data mode badge */}
            <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${
              isBackendMode
                ? "bg-blue-500/10 border-blue-500/30 text-blue-400"
                : "bg-gray-800 border-gray-700 text-gray-500"
            }`}>
              {isBackendMode ? "מצב נתונים: שרת" : "מצב נתונים: מקומי"}
            </span>
            {isBackendMode && isLoading && (
              <RefreshCw size={12} className="text-blue-400 animate-spin" />
            )}
          </div>
          <ProfileSwitcher />
        </div>
      </header>

      {/* Backend error banner */}
      {isBackendMode && apiError && (
        <div className="bg-red-950/60 border-b border-red-800/50 px-4 py-2 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-red-400 text-xs font-medium flex-shrink-0">שגיאה בחיבור לשרת</span>
            <span className="text-red-500/70 text-xs truncate">{apiError}</span>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            <span className="text-red-500/60 text-[10px]">שרת צריך לרוץ על http://127.0.0.1:8000</span>
            <button
              onClick={refreshFeed}
              className="flex items-center gap-1 text-xs text-red-300 hover:text-red-200 bg-red-900/40 hover:bg-red-900/60 border border-red-700/50 rounded px-2 py-0.5 transition-colors"
            >
              <RefreshCw size={10} />
              נסה שוב
            </button>
          </div>
        </div>
      )}

      {/* Desktop Nav */}
      <nav className="hidden md:block border-b border-gray-800 bg-gray-950/80">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex gap-1">
            {navItems.map(({ path, label, icon: Icon }) => {
              const active = location.pathname === path;
              return (
                <Link
                  key={path}
                  to={path}
                  className={`flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors border-b-2 ${
                    active
                      ? "text-emerald-400 border-emerald-400"
                      : "text-gray-400 border-transparent hover:text-gray-200 hover:border-gray-600"
                  }`}
                >
                  <Icon size={15} />
                  {label}
                </Link>
              );
            })}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        <Outlet />
      </main>

      {/* Mobile Bottom Nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-gray-950/95 border-t border-gray-800 backdrop-blur-sm z-50">
        <div className="flex">
          {navItems.map(({ path, label, icon: Icon }) => {
            const active = location.pathname === path;
            return (
              <Link
                key={path}
                to={path}
                className={`flex-1 flex flex-col items-center py-2 gap-1 text-xs transition-colors ${
                  active ? "text-emerald-400" : "text-gray-500"
                }`}
              >
                <Icon size={18} />
                <span className="text-[10px]">{label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}