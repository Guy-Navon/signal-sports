import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Clock, Inbox } from "lucide-react";
import Atmosphere from "@/components/shell/Atmosphere";
import SignalMark from "@/components/shell/SignalMark";
import EmptyState from "@/components/shared/EmptyState";
import ErrorState from "@/components/shared/ErrorState";
import { feedBodyState } from "@/components/feed/feedLoadModel";
import { filterFeedItems, toggleFilterSet } from "@/components/feed/feedFilters";
import OrbitFeedView from "@/components/feed/orbit/OrbitFeedView";
import OrbitLoadingState from "@/components/feed/orbit/OrbitLoadingState";
import "@/components/feed/orbit/orbit.css";
import { demoBanner, demoDecisionCounts, loadDemoSnapshot } from "./demoModel";

// The public read-only demo (#458). The feed and its explanations only: no
// router, no auth, no app provider, no API. It reads two static JSON files.

const PROFILE_NAME = "גיא";
const TICK_MS = 60_000;

function DemoBanner({ meta, now }) {
  const view = meta ? demoBanner(meta, now) : null;
  return (
    <div
      role="status"
      className="mb-4 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-border bg-surface-1/70 px-3 py-2 text-xs text-text-secondary"
    >
      <span className="font-medium text-signal-ai">הדגמה לקריאה בלבד</span>
      <span aria-hidden className="hidden sm:inline">·</span>
      <span>הפיד החי של הפרופיל של {PROFILE_NAME}, מתעדכן כל שעה</span>
      {view && (
        <>
          <span aria-hidden className="hidden sm:inline">·</span>
          <span className="inline-flex items-center gap-1">
            <Clock size={12} aria-hidden />
            {view.updated}
          </span>
        </>
      )}
      {view?.warning && (
        <span className="inline-flex basis-full items-center gap-1 text-signal-hidden">
          <AlertTriangle size={13} aria-hidden />
          {view.warning}
        </span>
      )}
    </div>
  );
}

export default function DemoApp() {
  const [snapshot, setSnapshot] = useState({ status: "loading", items: [], meta: null });
  const [now, setNow] = useState(() => Date.now());
  const [activeFilters, setActiveFilters] = useState(new Set(["all"]));

  const load = useCallback(() => {
    setSnapshot((current) => ({ ...current, status: "loading" }));
    loadDemoSnapshot(window.fetch.bind(window), import.meta.env.BASE_URL)
      .then(({ items, meta }) => {
        setSnapshot({ status: "ready", items, meta });
        setNow(Date.now());
      })
      .catch(() => setSnapshot({ status: "error", items: [], meta: null }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(id);
  }, []);

  const { items, meta, status } = snapshot;
  const filteredItems = useMemo(() => filterFeedItems(items, activeFilters), [items, activeFilters]);
  const decisionCounts = useMemo(() => demoDecisionCounts(items), [items]);
  const bodyState = feedBodyState({
    isBackendMode: true,
    isLoading: status === "loading",
    loadFailed: status === "error",
    itemCount: items.length,
  });

  return (
    <div className="orbit-product min-h-screen flex flex-col relative">
      <Atmosphere />
      <header className="orbit-masthead border-b border-transparent">
        <div className="max-w-screen-2xl mx-auto px-4 h-14 flex items-center gap-2">
          <SignalMark />
          <span className="orbit-wordmark font-display font-bold text-foreground text-[1.05rem] tracking-tight">
            <span>סיגנל</span>
            <small>מודיעין ספורט</small>
          </span>
        </div>
      </header>

      <main className="flex-1 w-full max-w-screen-2xl mx-auto px-4 pt-5 pb-12 md:px-5 md:pt-6">
        <DemoBanner meta={meta} now={now} />
        {bodyState === "loading" ? (
          <div className="orbit-feed-view">
            <OrbitLoadingState />
          </div>
        ) : bodyState === "error" ? (
          <div className="orbit-feed-view orbit-feed-empty" role="alert">
            <ErrorState
              variant="page"
              title="לא הצלחנו לטעון את ההדגמה"
              message="הנתונים לא נטענו. נסו שוב בעוד רגע."
              retryLabel="נסו שוב"
              onRetry={load}
            />
          </div>
        ) : bodyState === "empty" ? (
          <div className="orbit-feed-view orbit-feed-empty">
            <EmptyState
              icon={Inbox}
              title="אין כרגע סיפורים בפיד"
              hint="סיפורים חדשים יופיעו כאן בעדכון הבא."
            />
          </div>
        ) : (
          <OrbitFeedView
            readOnly
            items={filteredItems}
            localScoredArticles={[]}
            profileName={PROFILE_NAME}
            scanned={0}
            decisionCounts={decisionCounts}
            activeFilters={activeFilters}
            onToggleFilter={(id) => setActiveFilters((current) => toggleFilterSet(current, id))}
            onResetFilters={() => setActiveFilters(new Set(["all"]))}
          />
        )}
      </main>
    </div>
  );
}
