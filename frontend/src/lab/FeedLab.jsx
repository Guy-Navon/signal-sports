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

// Dev-only feed lab (#464): the new feed view on a real snapshot of the demo
// feed (dist-demo/demo-data, or SIGNAL_LAB_SNAPSHOT_DIR; see vite.lab.config.js).
// Nothing here reaches the main or demo bundles.
//
// lab.html?page=feed&case=<case>&ground=<soft|dark>&readonly=1
//   case=real      the snapshot exactly as exported
//   case=push      LAB FIXTURE: the first high_feed story re-marked as push
//   case=push2     LAB FIXTURE: the first two high_feed stories re-marked as push
//   case=pushlong  LAB FIXTURE: the story with the longest headline re-marked as push
// The fixtures only change a real story's decision, to see the lead block; the
// product never does this (no push, no lead).

const CASES = {
  real: (items) => items,
  push: (items) => asPush(items, firstHighFeed(items, 1)),
  push2: (items) => asPush(items, firstHighFeed(items, 2)),
  pushlong: (items) => (items.length ? asPush(items, [longestTitle(items)]) : items),
};

function firstHighFeed(items, count) {
  return items.filter((item) => item.score?.decision === "high_feed").slice(0, count);
}

function longestTitle(items) {
  const title = (item) => item.translatedTitle || item.title || "";
  return items.reduce((longest, item) => (title(item).length > title(longest).length ? item : longest));
}

/** LAB FIXTURE ONLY: re-mark the given stories as push and rank them first. */
function asPush(items, chosen) {
  const ids = new Set(chosen.map((item) => item.id));
  const pushed = chosen.map((item) => ({ ...item, score: { ...item.score, decision: "push" } }));
  return [...pushed, ...items.filter((item) => !ids.has(item.id))];
}

// Feedback controls need the app context. Saves here go nowhere: they resolve
// after a short pause so the "saving / saved" states can be seen.
const LAB_APP_CONTEXT = {
  addFeedback: () => new Promise((resolve) => setTimeout(resolve, 400)),
  neverShowArticle: () => new Promise((resolve) => setTimeout(resolve, 400)),
  isBackendMode: true,
  qaSurfaceAllowed: false,
  noteArticleOpened: () => {},
};

export default function FeedLab() {
  const params = new URLSearchParams(window.location.search);
  const caseName = CASES[params.get("case")] ? params.get("case") : "real";
  const { ground, setGround } = useGround();
  const readOnly = params.get("readonly") === "1";

  const [snapshot, setSnapshot] = useState({ status: "loading", items: [], meta: null, error: null });
  const [activeFilters, setActiveFilters] = useState(new Set(["all"]));

  useEffect(() => {
    loadDemoSnapshot(window.fetch.bind(window), "/")
      .then(({ items, meta }) => setSnapshot({ status: "ready", items, meta, error: null }))
      .catch((error) => setSnapshot({ status: "error", items: [], meta: null, error: String(error) }));
  }, []);

  const items = useMemo(() => CASES[caseName](snapshot.items), [caseName, snapshot.items]);
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
