import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Clock } from "lucide-react";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import { DEFAULT_GROUND } from "@/components/signal-ui/ground";
import { feedBodyState } from "@/components/feed/feedLoadModel";
import { toggleFilterSet } from "@/components/feed/feedFilters";
import SignalFeedView from "@/components/feed/signal/SignalFeedView";
import "@/components/shell/shell.css";
import { demoBanner, loadDemoSnapshot } from "./demoModel";
import "./demo.css";

// The public read-only demo (#458). The feed and its explanations only: no
// router, no auth, no app provider, no API. It reads static snapshot files only.

const PROFILE_NAME = "גיא";
const TICK_MS = 60_000;

function DemoBanner({ meta, now }) {
  const view = meta ? demoBanner(meta, now) : null;
  return (
    <div role="status" className="sg-demo-banner">
      <strong>הדגמה לקריאה בלבד</strong>
      <span aria-hidden="true">·</span>
      <span>הפיד החי של הפרופיל של {PROFILE_NAME}, מתעדכן כל שעה</span>
      {view && (
        <>
          <span aria-hidden="true">·</span>
          <span className="sg-demo-banner__time">
            <Clock size={12} aria-hidden="true" />
            {view.updated}
          </span>
        </>
      )}
      {view?.warning && (
        <span className="sg-demo-banner__warning">
          <AlertTriangle size={13} aria-hidden="true" />
          {view.warning}
        </span>
      )}
    </div>
  );
}

export default function DemoApp() {
  const [snapshot, setSnapshot] = useState({ status: "loading", items: [], results: [], meta: null });
  const [now, setNow] = useState(() => Date.now());
  const [activeFilters, setActiveFilters] = useState(new Set(["all"]));

  const load = useCallback(() => {
    setSnapshot((current) => ({ ...current, status: "loading" }));
    loadDemoSnapshot(window.fetch.bind(window), import.meta.env.BASE_URL)
      .then(({ items, meta, results }) => {
        setSnapshot({ status: "ready", items, meta, results });
        setNow(Date.now());
      })
      .catch(() => setSnapshot({ status: "error", items: [], results: [], meta: null }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(id);
  }, []);

  const { items, meta, results, status } = snapshot;
  const bodyState = feedBodyState({
    isBackendMode: true,
    isLoading: status === "loading",
    loadFailed: status === "error",
    itemCount: items.length,
  });

  return (
    <div className="signal-ui sg-shell sg-demo" data-ground={DEFAULT_GROUND}>
      <header className="sg-masthead sg-gutter sg-demo-masthead">
        <SignalWordmark className="sg-masthead__brand" />
      </header>

      <main className="sg-body">
        {bodyState !== "items" && (
          <div className="sg-gutter">
            <div className="sg-container"><DemoBanner meta={meta} now={now} /></div>
          </div>
        )}
        {bodyState === "loading" ? (
          <div className="sg-feed">
            <div className="sg-in sg-skeleton" role="status" aria-busy="true" aria-label="טוען את הפיד שלך">
              <i /><i /><i /><i /><i />
            </div>
          </div>
        ) : bodyState === "error" ? (
          <div className="sg-gutter sg-state" role="alert">
            <h2>לא הצלחנו לטעון את ההדגמה</h2>
            <p>הנתונים לא נטענו. נסו שוב בעוד רגע.</p>
            <button type="button" className="sg-more" onClick={load}>נסו שוב</button>
          </div>
        ) : bodyState === "empty" ? (
          <div className="sg-gutter sg-state" role="status">
            <h2>אין כרגע סיפורים בפיד</h2>
            <p>סיפורים חדשים יופיעו כאן בעדכון הבא.</p>
          </div>
        ) : (
          <SignalFeedView
            readOnly
            items={items}
            results={results}
            localScoredArticles={[]}
            status={<DemoBanner meta={meta} now={now} />}
            activeFilters={activeFilters}
            onToggleFilter={(id) => setActiveFilters((current) => toggleFilterSet(current, id))}
            onResetFilters={() => setActiveFilters(new Set(["all"]))}
          />
        )}
      </main>
    </div>
  );
}
