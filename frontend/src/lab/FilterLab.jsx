import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { SlidersHorizontal, X } from "lucide-react";
import SignalFeedView from "@/components/feed/signal/SignalFeedView";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import SignalStrength from "@/components/signal-ui/SignalStrength";
import FeedFilterBar, { FilterResult, LeaguePillRow } from "@/components/feed/signal/FeedFilterBar";
import { filterBarPills } from "@/components/feed/signal/feedLayoutModel";
import {
  ALL_LEAGUES_ID,
  ALL_LEVELS_ID,
  activeLeagueIds,
  filterFeedItems,
  hasActiveFilters,
  importanceOptions,
  toggleFilterSet,
  visibleCount,
} from "@/components/feed/feedFilters";
import { loadDemoSnapshot } from "@/demo/demoModel";
import { useGround } from "@/components/signal-ui/useGround";
import "@/components/shell/shell.css";
import { AppContext } from "@/context/appContextCore";
import { LAB_APP_CONTEXT, LAB_CASES, labCaseName } from "./labCases";
import "./filter-lab.css";

// Dev-only filter-bar lab (#483): three candidate filter bars on the real
// snapshot (dist-demo/demo-data or SIGNAL_LAB_SNAPSHOT_DIR, vite.lab.config.js),
// each driving the real SignalFeedView through its lab-only `filterBar` seam.
// Nothing here reaches the main or demo bundles.
//
// lab.html?page=filters&variant=a|b|c&case=real|push&filters=min:high_feed,league:NBA&chrome=0
//   a  one row: importance as a segmented control beside the league pills
//      (the recommendation; what the feed renders, FeedFilterBar)
//   b  two quiet rows: importance options with the signal mark and counts,
//      then the league pills
//   c  one "סינון" button opening a panel (popover on desktop, bottom sheet on
//      a phone) with importance, leagues and sources; active filters as
//      removable chips
// filters= preselects filter ids (for screenshots); chrome=0 hides the lab bar.

const VARIANTS = [
  { id: "a", label: "א · שורה אחת" },
  { id: "b", label: "ב · שתי שורות שקטות" },
  { id: "c", label: "ג · כפתור סינון" },
];

const DATE_FORMAT = new Intl.DateTimeFormat("he-IL", {
  weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Jerusalem",
});

/** The consumer masthead as it looks at the top of the page (static, lab only). */
function LabMasthead({ nowMs }) {
  return (
    <header className="sg-on-top sg-head" aria-label="כותרת לדוגמה">
      <div className="sg-gutter">
        <div className="sg-container sg-head__inner">
          <SignalWordmark className="sg-head__brand" />
          <p className="sg-head__date">{DATE_FORMAT.format(nowMs ?? Date.now())}</p>
          <div className="sg-tabs" aria-hidden="true">
            {["הפיד שלי", "תוצאות", "העדפות", "כיוונון"].map((label, index) => (
              <span key={label} className="sg-tab" aria-current={index === 0 ? "page" : undefined}>
                <span className="sg-tab__label">{label}</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </header>
  );
}

// ── Variant B: two quiet rows, importance with the signal mark ──────────────

/** The mark of a threshold: its lowest level's strokes ("הכול" = from נמוך). */
const thresholdMark = (level) => level ?? "low_feed";

function QuietImportance({ items, activeFilters, onToggle, className = "lab-imp" }) {
  const name = useId();
  const labelId = useId();
  const options = importanceOptions(items, activeFilters);
  return (
    <div className={className} role="radiogroup" aria-labelledby={labelId}>
      <span className="lab-imp__title" id={labelId}>חשיבות</span>
      {options.map((option) => (
        <label key={option.id} className="lab-imp__opt" data-filter={option.id} data-selected={option.selected || undefined}>
          <input
            type="radio"
            className="lab-imp__input"
            name={name}
            checked={option.selected}
            onChange={() => onToggle(option.level === null ? ALL_LEVELS_ID : option.id)}
          />
          <span className="lab-imp__mark" aria-hidden="true">
            <SignalStrength decision={thresholdMark(option.level)} />
          </span>
          <span>{option.label}</span>
          <span key={option.count} className="lab-imp__count sg-num sg-tick" dir="ltr" aria-hidden="true">
            {option.count}
          </span>
          <span className="sr-only">{`, ${option.count} סיפורים`}</span>
        </label>
      ))}
    </div>
  );
}

function VariantB({ items, activeFilters, shown, onToggle, onReset, enterBase }) {
  const shownAll = visibleCount(filterFeedItems(items, toggleFilterSet(activeFilters, ALL_LEAGUES_ID)));
  return (
    <div className="lab-fb">
      <QuietImportance items={items} activeFilters={activeFilters} onToggle={onToggle} />
      <LeaguePillRow items={items} activeFilters={activeFilters} onToggle={onToggle} enterBase={enterBase} shownAll={shownAll} />
      <FilterResult shown={shown} total={visibleCount(items)} activeFilters={activeFilters} onReset={onReset} />
    </div>
  );
}

// ── Variant C: one button, a panel, removable chips ──────────────────────────

/** LAB ONLY: source ids of a story (a cluster lists its members). */
function sourceIdsOf(item) {
  return item.type === "cluster" && item.sources?.length ? item.sources : [item.source];
}

function sourceNamesOf(item) {
  if (item.type === "cluster" && item.sources?.length) {
    return item.sources.map((id, index) => [id, item.sourceDisplayNames?.[index] ?? id]);
  }
  return [[item.source, item.sourceDisplayName ?? item.source]];
}

function useIsPhone() {
  const query = "(max-width: 900px)";
  const [phone, setPhone] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const list = matchMedia(query);
    const update = () => setPhone(list.matches);
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, []);
  return phone;
}

function VariantC({ items, activeFilters, shown, onToggle, onReset, sources, sourceFacets, onToggleSource, initialOpen }) {
  const [open, setOpen] = useState(initialOpen);
  const phone = useIsPhone();
  const buttonRef = useRef(null);
  const closeRef = useRef(null);
  const titleId = useId();
  const panelId = useId();
  const options = importanceOptions(items, activeFilters);
  const floor = options.find((option) => option.selected && option.level);
  const pills = filterBarPills(items, activeFilters);
  const leagues = new Set(activeLeagueIds(activeFilters));
  const chips = [
    ...(floor ? [{ id: floor.id, label: floor.label, remove: () => onToggle(ALL_LEVELS_ID) }] : []),
    ...pills.filter((pill) => leagues.has(pill.id)).map((pill) => ({
      id: pill.id, label: pill.label, remove: () => onToggle(pill.id),
    })),
    ...sourceFacets.filter((source) => sources.has(source.id)).map((source) => ({
      id: `source:${source.id}`, label: source.label, remove: () => onToggleSource(source.id),
    })),
  ];

  const close = () => {
    setOpen(false);
    buttonRef.current?.focus();
  };

  // Open: focus moves into the panel (its close button, first in order).
  // Escape closes and returns focus to the button.
  useEffect(() => {
    if (open && !initialOpen) closeRef.current?.focus();
  }, [open, initialOpen]);

  return (
    <div className="lab-fc">
      <div className="lab-fc__row">
        <button
          ref={buttonRef}
          type="button"
          className="lab-fc__btn"
          aria-expanded={open}
          aria-controls={panelId}
          aria-haspopup="dialog"
          onClick={() => (open ? close() : setOpen(true))}
        >
          <SlidersHorizontal size={16} aria-hidden="true" />
          סינון
          {chips.length > 0 && <span className="lab-fc__badge sg-num" dir="ltr">{chips.length}</span>}
        </button>
        {chips.length === 0 ? (
          <span className="lab-fc__hint">כל הפיד · <span className="sg-num" dir="ltr">{visibleCount(items)}</span></span>
        ) : (
          <ul className="lab-fc__chips" aria-label="סינון פעיל">
            {chips.map((chip) => (
              <li key={chip.id}>
                <button type="button" className="lab-fc__chip" onClick={chip.remove} aria-label={`הסרת סינון: ${chip.label}`}>
                  <bdi dir="auto">{chip.label}</bdi>
                  <X size={14} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <FilterResult shown={shown} total={visibleCount(items)} activeFilters={activeFilters} onReset={onReset} />
      {open && (
        <>
          {phone && <div className="lab-fc__scrim" onClick={close} aria-hidden="true" />}
          <div
            id={panelId}
            className="lab-fc__panel"
            role="dialog"
            aria-modal={phone}
            aria-labelledby={titleId}
            onKeyDown={(event) => event.key === "Escape" && close()}
          >
            <div className="lab-fc__head">
              <h2 id={titleId}>סינון</h2>
              <button ref={closeRef} type="button" className="lab-fc__close" onClick={close} aria-label="סגירה">
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            <section className="lab-fc__sec">
              <QuietImportance items={items} activeFilters={activeFilters} onToggle={onToggle} className="lab-imp lab-fc__imp" />
            </section>
            <section className="lab-fc__sec" aria-labelledby={`${panelId}-leagues`}>
              <h3 id={`${panelId}-leagues`}>ליגות</h3>
              {pills.map((pill) => (
                <label key={pill.id} className="lab-fc__check">
                  <input type="checkbox" checked={leagues.has(pill.id)} onChange={() => onToggle(pill.id)} />
                  <bdi dir="auto">{pill.label}</bdi>
                  <span className="sg-num" dir="ltr">{pill.count}</span>
                </label>
              ))}
            </section>
            <section className="lab-fc__sec" aria-labelledby={`${panelId}-sources`}>
              <h3 id={`${panelId}-sources`}>מקורות</h3>
              {sourceFacets.map((source) => (
                <label key={source.id} className="lab-fc__check">
                  <input type="checkbox" checked={sources.has(source.id)} onChange={() => onToggleSource(source.id)} />
                  <bdi dir="auto">{source.label}</bdi>
                  <span className="sg-num" dir="ltr">{source.count}</span>
                </label>
              ))}
            </section>
            <div className="lab-fc__foot">
              <button type="button" className="lab-fc__go" onClick={close}>
                הצגת <span className="sg-num" dir="ltr">{shown}</span> סיפורים
              </button>
              {(hasActiveFilters(activeFilters) || sources.size > 0) && (
                <button type="button" className="sg-filter-clear" onClick={onReset}>נקה הכול</button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── The page ─────────────────────────────────────────────────────────────────

function initialFilters(param) {
  const ids = (param ?? "").split(",").map((id) => id.trim()).filter(Boolean);
  return ids.reduce((set, id) => toggleFilterSet(set, id), new Set(["all"]));
}

export default function FilterLab() {
  const params = new URLSearchParams(window.location.search);
  const caseName = labCaseName(params.get("case"));
  const showChrome = params.get("chrome") !== "0";
  const { ground } = useGround();
  const [variant, setVariant] = useState(() =>
    VARIANTS.some((v) => v.id === params.get("variant")) ? params.get("variant") : "a"
  );
  const [snapshot, setSnapshot] = useState({ status: "loading", items: [], meta: null, error: null });
  const [activeFilters, setActiveFilters] = useState(() => initialFilters(params.get("filters")));
  // Variant C only, lab only: a source filter outside the shared filter model.
  const [sources, setSources] = useState(() => new Set());

  useEffect(() => {
    loadDemoSnapshot(window.fetch.bind(window), "/")
      .then(({ items, meta }) => setSnapshot({ status: "ready", items, meta, error: null }))
      .catch((error) => setSnapshot({ status: "error", items: [], meta: null, error: String(error) }));
  }, []);

  const allItems = useMemo(() => LAB_CASES[caseName](snapshot.items), [caseName, snapshot.items]);
  const items = useMemo(
    () => (variant === "c" && sources.size
      ? allItems.filter((item) => sourceIdsOf(item).some((id) => sources.has(id)))
      : allItems),
    [variant, sources, allItems]
  );
  const sourceFacets = useMemo(() => {
    const facets = new Map();
    for (const item of filterFeedItems(allItems, activeFilters)) {
      for (const [id, label] of sourceNamesOf(item)) {
        const facet = facets.get(id) ?? { id, label, count: 0 };
        facet.count += 1;
        facets.set(id, facet);
      }
    }
    return [...facets.values()].sort((a, b) => b.count - a.count);
  }, [allItems, activeFilters]);

  const nowMs = snapshot.meta?.generated_at ? Date.parse(snapshot.meta.generated_at) : undefined;
  const onToggle = (id) => setActiveFilters((current) => toggleFilterSet(current, id));
  const onReset = () => {
    setActiveFilters(new Set(["all"]));
    setSources(new Set());
  };
  const onToggleSource = (id) =>
    setSources((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  if (snapshot.status !== "ready") {
    return (
      <p className="lab-feed-note" role="status">
        {snapshot.status === "loading"
          ? "טוען את התמונה…"
          : `אין תמונת פיד: ${snapshot.error}. הריצו npm run build:demo עם נתונים, או הגדירו SIGNAL_LAB_SNAPSHOT_DIR.`}
      </p>
    );
  }

  const filterBar = {
    a: (bar) => <FeedFilterBar {...bar} />,
    b: (bar) => <VariantB {...bar} />,
    c: (bar) => (
      <VariantC
        {...bar}
        sources={sources}
        sourceFacets={sourceFacets}
        onToggleSource={onToggleSource}
        initialOpen={params.get("open") === "1"}
      />
    ),
  }[variant];

  return (
    <div className="signal-ui sg-shell lab-filters" data-ground={ground}>
      {showChrome && (
        <fieldset className="lab-ground-control lab-variant-control">
          <legend>סרגל סינון (#483)</legend>
          {VARIANTS.map(({ id, label }) => (
            <label key={id}>
              <input type="radio" name="variant" value={id} checked={variant === id} onChange={() => setVariant(id)} />
              {label}
            </label>
          ))}
        </fieldset>
      )}
      <LabMasthead nowMs={nowMs} />
      <AppContext.Provider value={LAB_APP_CONTEXT}>
      <SignalFeedView
        key={variant}
        items={items}
        activeFilters={activeFilters}
        onToggleFilter={onToggle}
        onResetFilters={onReset}
        nowMs={nowMs}
        filterBar={filterBar}
        status={
          caseName === "real" ? null : (
            <p className="lab-feed-fixture">תרחיש מעבדה: {caseName} (סיפור אמיתי שסומן push לבדיקה)</p>
          )
        }
      />
      </AppContext.Provider>
    </div>
  );
}
