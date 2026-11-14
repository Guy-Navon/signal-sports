import React, { useEffect, useMemo, useState } from "react";
import SignalFeedView from "@/components/feed/signal/SignalFeedView";
import { toggleFilterSet } from "@/components/feed/feedFilters";
import { AppContext } from "@/context/appContextCore";
import { loadDemoSnapshot } from "@/demo/demoModel";
import { GROUNDS } from "@/components/signal-ui/ground";
import { useGround } from "@/components/signal-ui/useGround";
import {
  AlertDialog, AlertDialogTrigger, AlertDialogContent, AlertDialogTitle,
  AlertDialogDescription, AlertDialogCancel,
} from "@/components/ui/alert-dialog";
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
  const { ground, setGround } = useGround();
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
      ground={ground === "light" ? undefined : ground}
      status={
        caseName === "real" ? null : (
          <p className="lab-feed-fixture">תרחיש מעבדה: {caseName} (סיפור אמיתי שסומן push לבדיקה)</p>
        )
      }
    />
  );

  return (
    <div className="signal-ui" data-ground={ground}>
      <fieldset className="lab-ground-control">
        <legend>רקע</legend>
        {GROUNDS.map(({ id, label }) => (
          <label key={id}>
            <input type="radio" name="ground" value={id} checked={ground === id}
              onChange={() => setGround(id)} />
            {label}
          </label>
        ))}
        <AlertDialog>
          <AlertDialogTrigger className="lab-dialog-trigger">בדיקת חלון</AlertDialogTrigger>
          <AlertDialogContent dir="rtl">
            <AlertDialogTitle>חלון ברקע הנבחר</AlertDialogTitle>
            <AlertDialogDescription>בדיקת צבעים, מקלדת ומיקוד בחלון שמוצג מחוץ לפיד.</AlertDialogDescription>
            <AlertDialogCancel>סגירה</AlertDialogCancel>
          </AlertDialogContent>
        </AlertDialog>
      </fieldset>
      {readOnly ? view : <AppContext.Provider value={LAB_APP_CONTEXT}>{view}</AppContext.Provider>}
    </div>
  );
}
