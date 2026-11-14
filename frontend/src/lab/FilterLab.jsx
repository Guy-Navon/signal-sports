import React, { useEffect, useMemo, useState } from "react";
import SignalFeedView from "@/components/feed/signal/SignalFeedView";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import FeedFilterBar from "@/components/feed/signal/FeedFilterBar";
import { toggleFilterSet } from "@/components/feed/feedFilters";
import { loadDemoSnapshot } from "@/demo/demoModel";
import { useGround } from "@/components/signal-ui/useGround";
import { AppContext } from "@/context/appContextCore";
import { LAB_APP_CONTEXT, LAB_CASES, labCaseName } from "./labCases";
import "@/components/shell/shell.css";
import "./filter-lab.css";

// The shipped C on the real snapshot. Historical A/B removed, 2026-11-14.
// lab.html?page=filters&case=real|push&filters=min:high_feed,league:NBA,source:one&open=1&chrome=0
const DATE_FORMAT = new Intl.DateTimeFormat("he-IL", {
  weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Jerusalem",
});

function LabMasthead({ nowMs }) {
  return (
    <header className="sg-on-top sg-head" aria-label="כותרת לדוגמה">
      <div className="sg-gutter"><div className="sg-container sg-head__inner">
        <SignalWordmark className="sg-head__brand" />
        <p className="sg-head__date">{DATE_FORMAT.format(nowMs ?? Date.now())}</p>
        <div className="sg-tabs" aria-hidden="true">
          {["הפיד שלי", "תוצאות", "העדפות", "כיוונון"].map((label, index) => (
            <span key={label} className="sg-tab" aria-current={index === 0 ? "page" : undefined}>
              <span className="sg-tab__label">{label}</span>
            </span>
          ))}
        </div>
      </div></div>
    </header>
  );
}

function initialFilters(param) {
  return (param ?? "").split(",").map((id) => id.trim()).filter(Boolean)
    .reduce((set, id) => toggleFilterSet(set, id), new Set(["all"]));
}

export default function FilterLab() {
  const params = new URLSearchParams(window.location.search);
  const caseName = labCaseName(params.get("case"));
  const { ground } = useGround();
  const [snapshot, setSnapshot] = useState({ status: "loading", items: [], meta: null, error: null });
  const [activeFilters, setActiveFilters] = useState(() => initialFilters(params.get("filters")));
  useEffect(() => {
    loadDemoSnapshot(window.fetch.bind(window), "/")
      .then(({ items, meta }) => setSnapshot({ status: "ready", items, meta, error: null }))
      .catch((error) => setSnapshot({ status: "error", items: [], meta: null, error: String(error) }));
  }, []);
  const items = useMemo(() => LAB_CASES[caseName](snapshot.items), [caseName, snapshot.items]);
  if (snapshot.status !== "ready") {
    return <p className="lab-feed-note" role="status">{snapshot.status === "loading" ? "טוען את התמונה…"
      : `אין תמונת פיד: ${snapshot.error}. הריצו npm run build:demo עם נתונים, או הגדירו SIGNAL_LAB_SNAPSHOT_DIR.`}</p>;
  }
  const nowMs = snapshot.meta?.generated_at ? Date.parse(snapshot.meta.generated_at) : undefined;
  return (
    <div className="signal-ui sg-shell lab-filters" data-ground={ground}>
      {params.get("chrome") !== "0" && <p className="lab-feed-note">סינון (#483) · ג · הגרסה שנבחרה</p>}
      <LabMasthead nowMs={nowMs} />
      <AppContext.Provider value={LAB_APP_CONTEXT}>
        <SignalFeedView items={items} activeFilters={activeFilters}
          onToggleFilter={(id) => setActiveFilters((current) => toggleFilterSet(current, id))}
          onResetFilters={() => setActiveFilters(new Set(["all"]))} nowMs={nowMs}
          filterBar={(bar) => <FeedFilterBar {...bar} initialOpen={params.get("open") === "1"} />}
          status={caseName === "real" ? null : <p className="lab-feed-fixture">תרחיש מעבדה: {caseName} (סיפור אמיתי שסומן push לבדיקה)</p>} />
      </AppContext.Provider>
    </div>
  );
}
