import React, { useEffect, useMemo, useRef, useState } from "react";
import SignalFeedView from "@/components/feed/signal/SignalFeedView";
import { latestStories, leaguePills } from "@/components/feed/signal/feedLayoutModel";
import { latestFinals } from "@/components/feed/signal/resultsStripModel";
import { orbitStoryId } from "@/components/feed/orbit/orbitStoryModel";
import { toggleFilterSet } from "@/components/feed/feedFilters";
import { normalizeResultsResponse } from "@/components/results/resultsModel";
import { AppContext } from "@/context/appContextCore";
import { loadDemoSnapshot } from "@/demo/demoModel";
import { mockResults } from "@/data/mockResults";
import { LAB_APP_CONTEXT, LAB_CASES, labCaseName } from "./labCases";

// Dev-only motion lab (#467): the new feed on the real snapshot, with controls
// to replay what the motion responds to. Nothing here reaches the main or demo
// bundles.
//
// lab.html?page=motion&case=<real|push|...>&ground=<soft|dark>
//
// - Replay load: remounts the feed, so the first-load choreography plays again.
// - Refresh: the newest stories (and the newest result) are held back until
//   the refresh button, then arrive the way a refetch delivers them. They are
//   real stories from the snapshot; only their timing is staged.
// - Filter: presses the league pill with the most stories, then "all".
// - Reduced motion (simulated): the same "animation: none" the feed's
//   prefers-reduced-motion rule applies. The OS setting is the real test.
// Results: the snapshot's results.json when it has one; otherwise the local
// mock results, labelled as a fixture.

const HELD_STORIES = 3;
const REHOLD_PAUSE_MS = 900;

function heldBack(items, results, nowMs) {
  const stories = new Set(
    latestStories(items, { localScoredArticles: [] }).slice(0, HELD_STORIES).map(orbitStoryId)
  );
  const newestGame = latestFinals(results, nowMs)[0];
  return { stories, gameId: newestGame?.id ?? null };
}

export default function MotionLab() {
  const params = new URLSearchParams(window.location.search);
  const caseName = labCaseName(params.get("case"));
  const groundParam = params.get("ground");
  const ground = groundParam === "soft" || groundParam === "dark" ? groundParam : undefined;

  const [snapshot, setSnapshot] = useState({ status: "loading", items: [], results: [], meta: null, error: null });
  const [mount, setMount] = useState(0);
  const [held, setHeld] = useState(true);
  const [reduce, setReduce] = useState(false);
  const [activeFilters, setActiveFilters] = useState(new Set(["all"]));
  const rehold = useRef(null);

  useEffect(() => {
    loadDemoSnapshot(window.fetch.bind(window), "/")
      .then(({ items, meta, results }) => setSnapshot({ status: "ready", items, meta, results, error: null }))
      .catch((error) => setSnapshot({ status: "error", items: [], results: [], meta: null, error: String(error) }));
    return () => clearTimeout(rehold.current);
  }, []);

  const nowMs = snapshot.meta?.generated_at ? Date.parse(snapshot.meta.generated_at) : undefined;
  const resultsFixture = snapshot.results.length === 0;
  const allResults = useMemo(
    () => (resultsFixture ? normalizeResultsResponse({ games: mockResults }).games : snapshot.results),
    [resultsFixture, snapshot.results]
  );
  const allItems = useMemo(() => LAB_CASES[caseName](snapshot.items), [caseName, snapshot.items]);
  const hold = useMemo(() => heldBack(allItems, allResults, nowMs), [allItems, allResults, nowMs]);
  const items = useMemo(
    () => (held ? allItems.filter((item) => !hold.stories.has(orbitStoryId(item))) : allItems),
    [held, allItems, hold]
  );
  const results = useMemo(
    () => (held ? allResults.filter((game) => game.id !== hold.gameId) : allResults),
    [held, allResults, hold]
  );
  const topPill = useMemo(() => leaguePills(allItems)[0] ?? null, [allItems]);
  const filtered = !activeFilters.has("all");

  const replayLoad = () => {
    clearTimeout(rehold.current);
    setActiveFilters(new Set(["all"]));
    setHeld(true);
    setMount((value) => value + 1);
  };

  const refresh = () => {
    clearTimeout(rehold.current);
    if (held) {
      setHeld(false);
      return;
    }
    // Already released: hold them back again (removal is instant), then let
    // them arrive once more.
    setHeld(true);
    rehold.current = setTimeout(() => setHeld(false), REHOLD_PAUSE_MS);
  };

  const toggleFilter = () => {
    if (!topPill) return;
    setActiveFilters(filtered ? new Set(["all"]) : toggleFilterSet(new Set(["all"]), topPill.id));
  };

  if (snapshot.status !== "ready") {
    return (
      <p className="lab-feed-note" role="status">
        {snapshot.status === "loading"
          ? "טוען את התמונה…"
          : `אין תמונת פיד: ${snapshot.error}. הריצו npm run build:demo עם נתונים, או הגדירו SIGNAL_LAB_SNAPSHOT_DIR.`}
      </p>
    );
  }

  return (
    <div className={reduce ? "lab-motion lab-reduce" : "lab-motion"}>
      <div className="lab-motion__bar" role="toolbar" aria-label="בקרי מעבדת תנועה">
        <b>מעבדת תנועה</b>
        <button type="button" data-lab="replay" onClick={replayLoad}>נגן שוב את הטעינה</button>
        <button type="button" data-lab="refresh" onClick={refresh}>
          {held ? `רענון: ${hold.stories.size} סיפורים חדשים מגיעים` : "רענון שוב"}
        </button>
        <button type="button" data-lab="filter" onClick={toggleFilter} disabled={!topPill} aria-pressed={filtered}>
          {filtered ? "חזרה להכול" : `סינון: ${topPill?.label ?? "אין ליגות"}`}
        </button>
        <label className="lab-motion__toggle">
          <input type="checkbox" data-lab="reduce" checked={reduce} onChange={(event) => setReduce(event.target.checked)} />
          תנועה מופחתת (הדמיה)
        </label>
        <span className="lab-dim">
          {caseName === "real" ? (
            <a href="?page=motion&case=push">הצג בלוק פתיחה (תרחיש push)</a>
          ) : (
            <a href="?page=motion">חזרה לתמונה האמיתית</a>
          )}
        </span>
      </div>

      <AppContext.Provider value={LAB_APP_CONTEXT}>
        <SignalFeedView
          key={mount}
          items={items}
          results={results}
          activeFilters={activeFilters}
          onToggleFilter={(id) => setActiveFilters((current) => toggleFilterSet(current, id))}
          onResetFilters={() => setActiveFilters(new Set(["all"]))}
          nowMs={nowMs}
          ground={ground}
          status={
            caseName === "real" && !resultsFixture ? null : (
              <p className="lab-feed-fixture">
                {[
                  caseName !== "real" && `תרחיש מעבדה: ${caseName} (סיפור אמיתי שסומן push לבדיקה)`,
                  resultsFixture && "תוצאות: נתוני דמה מקומיים (אין results.json בתמונה)",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            )
          }
        />
      </AppContext.Provider>
    </div>
  );
}
