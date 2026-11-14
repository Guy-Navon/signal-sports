import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { SlidersHorizontal, X } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import {
  ALL_LEVELS_ID, ALL_LEAGUES_ID, activeLeagueIds, activeSourceIds, hasActiveFilters,
  filterFeedItems, importanceOptions, sourceOptions, toggleFilterSet, visibleCount,
} from "@/components/feed/feedFilters";
import { filterBarPills, filterResultLine } from "./feedLayoutModel";

function useIsPhone() {
  const query = "(width < 900px)";
  const [phone, setPhone] = useState(() => typeof window !== "undefined" && Boolean(window.matchMedia?.(query).matches));
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    const media = window.matchMedia(query);
    const update = () => setPhone(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return phone;
}

/** Native radios preserve the browser's RTL arrow-key behaviour. */
export function ImportanceControl({ items, activeFilters, onToggle }) {
  const name = useId();
  const options = importanceOptions(items, activeFilters);
  return (
    <div className="sg-seg" role="radiogroup" aria-label="סינון לפי חשיבות">
      {options.map((option) => (
        <label key={option.id} className="sg-seg__opt" data-filter={option.id} data-selected={option.selected || undefined}>
          <input type="radio" className="sg-seg__input" name={name} value={option.id}
            checked={option.selected} onChange={() => onToggle(option.level === null ? ALL_LEVELS_ID : option.id)} />
          <span className="sg-seg__label">{option.label}</span>
          <span className="sg-seg__count sg-num" dir="ltr" aria-hidden="true">{option.count}</span>
          <span className="sr-only">{`, ${option.count} סיפורים`}</span>
        </label>
      ))}
    </div>
  );
}

/** The single, persistently mounted filter-change announcement. */
export function FilterResult({ shown, total, activeFilters }) {
  const line = filterResultLine(shown, total, activeFilters);
  return (
    <div className="sg-filter-result" data-active={Boolean(line) && shown > 0 || undefined}>
      <span role="status" aria-atomic="true">{line}</span>
    </div>
  );
}

function FacetOptions({ options, activeFilters, onToggle }) {
  return (
    <div className="sg-filter-options">
      {options.map((option) => (
        <label key={option.id} className="sg-filter-check" data-filter={option.id}>
          <input type="checkbox" checked={activeFilters.has(option.id)} onChange={() => onToggle(option.id)} />
          <bdi dir="auto">{option.label}</bdi>
          <span className="sg-num" dir="ltr">{option.count}</span>
        </label>
      ))}
    </div>
  );
}

function LeagueOptions({ items, options, activeFilters, onToggle }) {
  const allCount = visibleCount(filterFeedItems(items, toggleFilterSet(activeFilters, ALL_LEAGUES_ID)));
  return <div className="sg-filter-options">
    <button type="button" className="sg-pill sg-pill--all" aria-pressed={activeLeagueIds(activeFilters).length === 0}
      onClick={() => onToggle(ALL_LEAGUES_ID)}>כל הליגות<span className="sg-num" dir="ltr">{allCount}</span></button>
    {options.map((option, index) => <button key={option.id} type="button" className="sg-pill"
      data-filter={option.id} data-tint={(index % 4) + 1} aria-pressed={activeFilters.has(option.id)} onClick={() => onToggle(option.id)}>
      <i className="sg-pill__mark" aria-hidden="true" /><bdi dir="auto">{option.label}</bdi><span className="sg-num" dir="ltr">{option.count}</span>
    </button>)}
  </div>;
}

/** Desktop disclosure; native modal dialog on phones supplies background inertness. */
function FilterPanel({ phone, panelId, items, activeFilters, shown, leagues, sources, onToggle, onReset, onClose }) {
  const panelRef = useRef(null);
  const closeRef = useRef(null);
  const lastRef = useRef(null);
  useEffect(() => {
    if (phone) panelRef.current?.showModal();
    closeRef.current?.focus({ preventScroll: true });
    if (!phone || typeof document === "undefined") return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const dialog = panelRef.current;
    return () => {
      dialog?.close();
      document.body.style.overflow = previous;
    };
  }, [phone]);

  const Panel = phone ? "dialog" : "div";
  return (
    <Panel ref={panelRef} id={panelId} className="sg-filter-panel" aria-labelledby={`${panelId}-title`}
      role={phone ? undefined : "region"} aria-modal={phone ? true : undefined}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => {
        if (!phone || event.target !== panelRef.current) return;
        const rect = panelRef.current.getBoundingClientRect();
        if (event.clientY < rect.top || event.clientY > rect.bottom || event.clientX < rect.left || event.clientX > rect.right) onClose();
      }}
      onKeyDown={(event) => {
        if (!phone || event.key !== "Tab") return;
        if (event.shiftKey && event.target === closeRef.current) {
          event.preventDefault(); lastRef.current?.focus();
        } else if (!event.shiftKey && event.target === lastRef.current) {
          event.preventDefault(); closeRef.current?.focus();
        }
      }}>
      <div className="sg-filter-panel__head">
        <h2 id={`${panelId}-title`}>סינון</h2>
        <button ref={closeRef} type="button" className="sg-filter-close" onClick={onClose} aria-label="סגירת סינון">
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <div className="sg-filter-panel__columns">
        <section className="sg-filter-section" aria-labelledby={`${panelId}-importance`}>
          <h3 id={`${panelId}-importance`}>חשיבות</h3>
          <ImportanceControl items={items} activeFilters={activeFilters} onToggle={onToggle} />
        </section>
        <section className="sg-filter-section" aria-labelledby={`${panelId}-leagues`}>
          <h3 id={`${panelId}-leagues`}>ליגות</h3>
          <LeagueOptions items={items} options={leagues} activeFilters={activeFilters} onToggle={onToggle} />
        </section>
        <section className="sg-filter-section" aria-labelledby={`${panelId}-sources`}>
          <h3 id={`${panelId}-sources`}>מקורות</h3>
          <FacetOptions options={sources} activeFilters={activeFilters} onToggle={onToggle} />
        </section>
      </div>
      <div className="sg-filter-panel__foot">
        <button type="button" className="sg-filter-clear" onClick={onReset}>נקה הכול</button>
        <button ref={lastRef} type="button" className="sg-filter-done" onClick={onClose}>
          {phone ? <>הצג <span className="sg-num" dir="ltr">{shown}</span> סיפורים</> : "סגור"}
        </button>
      </div>
    </Panel>
  );
}

/** Variant C, chosen by Guy 2026-11-14. Filters apply live, without persistence. */
export default function FeedFilterBar({ items, activeFilters, shown, onToggle, onReset, initialOpen = false }) {
  const [open, setOpen] = useState(initialOpen);
  const phone = useIsPhone();
  const reducedMotion = useReducedMotion();
  const buttonRef = useRef(null);
  const rootRef = useRef(null);
  const wasOpen = useRef(initialOpen);
  const panelId = useId();
  const leagues = useMemo(() => filterBarPills(items, activeFilters), [items, activeFilters]);
  const sources = useMemo(() => sourceOptions(items, activeFilters), [items, activeFilters]);
  const floor = importanceOptions(items, activeFilters).find((option) => option.selected && option.level);
  const labels = new Map([...leagues, ...sources].map((option) => [option.id, option.label]));
  const chips = [
    ...(floor ? [{ id: floor.id, label: floor.label }] : []),
    ...[...activeLeagueIds(activeFilters), ...activeSourceIds(activeFilters)]
      .map((id) => ({ id, label: labels.get(id) ?? id.slice(id.indexOf(":") + 1) })),
  ];
  const close = useCallback(() => {
    setOpen(false);
  }, []);
  useEffect(() => {
    // A modal makes the trigger inert until its dialog has unmounted. Restore
    // focus in the owning view after that commit, including initially open labs.
    if (!open && wasOpen.current) buttonRef.current?.focus({ preventScroll: true });
    wasOpen.current = open;
  }, [open]);
  useEffect(() => {
    if (!open || typeof document === "undefined") return undefined;
    const escape = (event) => {
      if (event.key === "Escape") { event.preventDefault(); close(); }
    };
    const outside = (event) => {
      if (!phone && !rootRef.current?.contains(event.target)) close();
    };
    document.addEventListener("keydown", escape);
    document.addEventListener("click", outside);
    return () => {
      document.removeEventListener("keydown", escape);
      document.removeEventListener("click", outside);
    };
  }, [open, phone, close]);

  const panel = open ? <FilterPanel key={phone ? "sheet" : "panel"} phone={phone} panelId={panelId}
    items={items} activeFilters={activeFilters} shown={shown} leagues={leagues} sources={sources}
    onToggle={onToggle} onReset={onReset} onClose={close} /> : null;

  return (
    <div ref={rootRef} className="sg-filters" data-filtered={hasActiveFilters(activeFilters) || undefined}>
      <div className="sg-filters__row">
        <button ref={buttonRef} type="button" className="sg-filter-toggle" aria-expanded={open}
          aria-controls={panelId} aria-haspopup={phone ? "dialog" : undefined} onClick={() => open ? close() : setOpen(true)}>
          <SlidersHorizontal size={16} aria-hidden="true" />סינון
          {chips.length > 0 && <span className="sg-filter-badge sg-num" dir="ltr">{chips.length}</span>}
        </button>
        {chips.length > 0 && <ul className="sg-filter-chips" aria-label="סינון פעיל">
          {chips.map((chip) => <li key={chip.id}>
            <button type="button" className="sg-filter-chip" data-filter={chip.id}
              onClick={() => { onToggle(chip.id); buttonRef.current?.focus({ preventScroll: true }); }}
              aria-label={`הסרת סינון: ${chip.label}`}>
              <bdi dir="auto">{chip.label}</bdi><X size={14} aria-hidden="true" />
            </button>
          </li>)}
        </ul>}
        {chips.length > 0 && <button type="button" className="sg-filter-clear" onClick={() => {
          onReset(); buttonRef.current?.focus({ preventScroll: true });
        }}>נקה סינון</button>}
      </div>
      {phone ? panel : open && <motion.div className="sg-filter-reveal"
        initial={reducedMotion ? false : { height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
        transition={{ duration: reducedMotion ? 0 : 0.2, ease: [0.2, 0.8, 0.2, 1] }}>{panel}</motion.div>}
      <FilterResult shown={shown} total={visibleCount(items)} activeFilters={activeFilters} />
    </div>
  );
}
