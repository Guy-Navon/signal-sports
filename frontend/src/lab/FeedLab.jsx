import React, { useEffect, useMemo, useState } from "react";
import SignalFeedView from "@/components/feed/signal/SignalFeedView";
import { toggleFilterSet } from "@/components/feed/feedFilters";
import { AppContext } from "@/context/appContextCore";
import { loadDemoSnapshot } from "@/demo/demoModel";
import { LAB_APP_CONTEXT, LAB_CASES, labCaseName } from "./labCases";

// Dev-only feed lab (#464): the new feed view on a real snapshot of the demo
// feed (dist-demo/demo-data, or SIGNAL_LAB_SNAPSHOT_DIR; see vite.lab.config.js).
// Nothing here reaches the main or demo bundles.
//
// lab.html?page=feed&case=<case>&ground=<soft|dark>&readonly=1
// Cases (real, push, push2, pushlong) are described in labCases.js.

export default function FeedLab() {
  const params = new URLSearchParams(window.location.search);
  const caseName = labCaseName(params.get("case"));
  const groundParam = params.get("ground");
  const ground = groundParam === "soft" || groundParam === "dark" ? groundParam : undefined;
  const readOnly = params.get("readonly") === "1";

  const [snapshot, setSnapshot] = useState({ status: "loading", items: [], meta: null, error: null });
  const [activeFilters, setActiveFilters] = useState(new Set(["all"]));

  useEffect(() => {
    loadDemoSnapshot(window.fetch.bind(window), "/")
      .then(({ items, meta }) => setSnapshot({ status: "ready", items, meta, error: null }))
      .catch((error) => setSnapshot({ status: "error", items: [], meta: null, error: String(error) }));
  }, []);

  const items = useMemo(() => LAB_CASES[caseName](snapshot.items), [caseName, snapshot.items]);
  const nowMs = snapshot.meta?.generated_at ? Date.parse(snapshot.meta.generated_at) : undefined;

  if (snapshot.status !== "ready") {
    return (
      <p className="lab-feed-note" role="status">
        {snapshot.status === "loading"
          ? "טוען את התמונה…"
          : `אין תמונת פיד: ${snapshot.error}. הריצו npm run build:demo עם נתונים, או הגדירו SIGNAL_LAB_SNAPSHOT_DIR.`}
      </p>
    );
  }

  const view = (
    <SignalFeedView
      items={items}
      activeFilters={activeFilters}
      onToggleFilter={(id) => setActiveFilters((current) => toggleFilterSet(current, id))}
      onResetFilters={() => setActiveFilters(new Set(["all"]))}
      readOnly={readOnly}
      nowMs={nowMs}
      ground={ground}
      status={
        caseName === "real" ? null : (
          <p className="lab-feed-fixture">תרחיש מעבדה: {caseName} (סיפור אמיתי שסומן push לבדיקה)</p>
        )
      }
    />
  );

  return readOnly ? view : <AppContext.Provider value={LAB_APP_CONTEXT}>{view}</AppContext.Provider>;
}
