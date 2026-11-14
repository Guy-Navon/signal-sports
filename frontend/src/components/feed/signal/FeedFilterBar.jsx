import React, { useId, useMemo } from "react";
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
import { filterBarPills, filterResultLine } from "./feedLayoutModel";
import { enterStyle } from "./feedMotionModel";

// The feed's filter bar (#483, variant A of lab.html?page=filters): the
// importance threshold as a segmented control beside the league pills (one
// row on desktop, stacked on a phone), and a quiet "showing X of N" line with
// a clear-all while anything is filtered. Filters only narrow what the engine
// already chose to show (feedFilters); nothing here ranks, scores or reveals
// a hidden story.

const PILL_TINTS = 4;

/**
 * The importance threshold ("הכול", "רגיל ומעלה", "חשוב ומעלה") as native
 * radios under a segmented look: one choice, arrow keys move and choose
 * (RTL-aware, from the browser), and each option's name carries its count
 * ("חשוב ומעלה, 10 סיפורים").
 */
export function ImportanceControl({ items, activeFilters, onToggle, enterBase = 0 }) {
  const name = useId();
  const options = useMemo(() => importanceOptions(items, activeFilters), [items, activeFilters]);
  const choose = (option) => onToggle(option.level === null ? ALL_LEVELS_ID : option.id);
  return (
    <div className="sg-seg" role="radiogroup" aria-label="סינון לפי חשיבות" style={enterStyle(0, enterBase)}>
      {options.map((option) => (
        <label
          key={option.id}
          className="sg-seg__opt"
          data-filter={option.id}
          data-selected={option.selected || undefined}
        >
          <input
            type="radio"
            className="sg-seg__input"
            name={name}
            value={option.id}
            checked={option.selected}
            onChange={() => choose(option)}
          />
          <span className="sg-seg__label">{option.label}</span>
          <span key={option.count} className="sg-seg__count sg-num sg-tick" dir="ltr" aria-hidden="true">
            {option.count}
          </span>
          <span className="sr-only">{`, ${option.count} סיפורים`}</span>
        </label>
      ))}
    </div>
  );
}

/**
 * The league pills (B6): "כל הליגות" clears the leagues only (the threshold
 * stays); each count is what pressing it would show under the threshold.
 */
export function LeaguePillRow({ items, activeFilters, onToggle, enterBase = 0, shownAll }) {
  const pills = useMemo(() => filterBarPills(items, activeFilters), [items, activeFilters]);
  if (pills.length === 0) return null;
  const selected = new Set(activeLeagueIds(activeFilters));
  const noLeague = selected.size === 0;
  return (
    <div className="sg-pills" role="group" aria-label="סינון לפי ליגה">
      <button
        type="button"
        className="sg-pill sg-pill--all"
        aria-pressed={noLeague}
        onClick={() => onToggle(ALL_LEAGUES_ID)}
        style={enterStyle(0, enterBase)}
      >
        <i className="sg-pill__mark" aria-hidden="true" />
        <b>כל הליגות</b>
        <span key={shownAll} className="sg-num sg-tick" dir="ltr">{shownAll}</span>
      </button>
      {pills.map((pill, index) => (
        <button
          type="button"
          key={pill.id}
          className="sg-pill"
          data-tint={(index % PILL_TINTS) + 1}
          data-filter={pill.id}
          aria-pressed={selected.has(pill.id)}
          onClick={() => onToggle(pill.id)}
          style={enterStyle(index + 1, enterBase)}
        >
          <i className="sg-pill__mark" aria-hidden="true" />
          <b><bdi dir="auto">{pill.label}</bdi></b>
          <span key={pill.count} className="sg-num sg-tick" dir="ltr">{pill.count}</span>
        </button>
      ))}
    </div>
  );
}

/**
 * "מוצגים X מתוך N סיפורים · נקה סינון" while anything is filtered. The line
 * is a polite live region, so a change of filter is announced once, as the
 * number of stories now shown. With nothing shown the feed's empty state
 * speaks (and offers the way back), so the line is announced but not drawn.
 */
export function FilterResult({ shown, total, activeFilters, onReset }) {
  const line = filterResultLine(shown, total, activeFilters);
  const drawn = Boolean(line) && shown > 0;
  return (
    <div className="sg-filter-result" data-active={drawn || undefined}>
      <span role="status">{line}</span>
      {drawn && (
        <button type="button" className="sg-filter-clear" onClick={onReset}>
          נקה סינון
        </button>
      )}
    </div>
  );
}

/**
 * The bar as the feed renders it.
 * @param {{
 *   items: any[],
 *   activeFilters: Set<string>,
 *   shown: number,
 *   onToggle: (id: string) => void,
 *   onReset: () => void,
 *   enterBase?: number,
 * }} props
 */
export default function FeedFilterBar({ items, activeFilters, shown, onToggle, onReset, enterBase = 0 }) {
  // "כל הליגות" counts what clearing the leagues would show.
  const shownAll = useMemo(
    () => visibleCount(filterFeedItems(items, toggleFilterSet(activeFilters, ALL_LEAGUES_ID))),
    [items, activeFilters]
  );
  return (
    <div className="sg-filters" data-filtered={hasActiveFilters(activeFilters) || undefined}>
      <div className="sg-filters__row">
        <ImportanceControl items={items} activeFilters={activeFilters} onToggle={onToggle} enterBase={enterBase} />
        <span className="sg-filters__sep" aria-hidden="true" />
        <LeaguePillRow
          items={items}
          activeFilters={activeFilters}
          onToggle={onToggle}
          enterBase={enterBase}
          shownAll={shownAll}
        />
      </div>
      <FilterResult shown={shown} total={visibleCount(items)} activeFilters={activeFilters} onReset={onReset} />
    </div>
  );
}
