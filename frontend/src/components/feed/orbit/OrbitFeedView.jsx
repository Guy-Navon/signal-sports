import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowUpLeft,
  ChevronLeft,
  Layers3,
  RotateCcw,
  SlidersHorizontal,
} from "lucide-react";
import { cn } from "@/lib/utils";
import EmptyState from "@/components/shared/EmptyState";
import FeedbackControls from "@/components/feed/FeedbackControls";
import SourceMeta from "@/components/feed/SourceMeta";
import { buildKicker } from "@/components/feed/storyLabels";
import { getDecisionConfig } from "@/components/feed/decisionConfig";
import {
  LEVEL_FILTER_IDS,
  TOPIC_CHIPS,
} from "@/components/feed/feedFilters";
import OrbitStoryField from "./OrbitStoryField";
import {
  queueEnterMotion,
  queueEnterTransition,
  queuePage,
} from "./orbitQueueMotion";
import {
  orbitFeedbackArticleId,
  orbitHasMultiSourceField,
  orbitQueueItems,
  orbitStoryId,
  orbitStoryReports,
  orbitStorySourceLine,
  orbitStoryTimestamp,
  orbitStoryTitle,
  orbitUniqueSourceCount,
  resolveOrbitFocus,
} from "./orbitStoryModel";

function OrbitFeedHeading({ profileName, total, scanned, urgentCount }) {
  return (
    <header className="orbit-feed-heading">
      <div>
        <span className="orbit-feed-heading__eyebrow">
          <i aria-hidden />
          המרחב האישי שלך
        </span>
        <h1>
          {urgentCount > 0
            ? `${urgentCount} אותות משנים מסלול עכשיו`
            : "הסיפורים החשובים מתכנסים כאן"}
        </h1>
        <p>
          {profileName ? `הדירוג של ${profileName}` : "הדירוג האישי"} מציב את הסיפור
          החשוב במרכז ואת המקורות סביבו.
        </p>
      </div>
      <div className="orbit-feed-heading__stats" aria-label="מצב הפיד">
        <span>
          <strong dir="ltr">{total}</strong>
          סיפורים במסלול
        </span>
        {scanned > 0 && (
          <span>
            <strong dir="ltr">{scanned}</strong>
            דיווחים נסרקו
          </span>
        )}
      </div>
    </header>
  );
}

function OrbitFilters({
  activeFilters,
  decisionCounts,
  shownCount,
  totalCount,
  onToggle,
  onReset,
}) {
  const filtered = !activeFilters.has("all");

  return (
    <div className="orbit-filters">
      <div className="orbit-filters__label">
        <SlidersHorizontal size={15} aria-hidden />
        <span>כיוון המסלול</span>
      </div>
      <div className="orbit-filters__track scrollbar-hide" aria-label="סינון הפיד">
        <button
          type="button"
          onClick={onReset}
          aria-pressed={!filtered}
          className={cn("orbit-filter", !filtered && "is-active")}
        >
          הכול
          <span dir="ltr">{totalCount}</span>
        </button>
        {LEVEL_FILTER_IDS.map((id) => (
          <button
            type="button"
            key={id}
            onClick={() => onToggle(id)}
            aria-pressed={activeFilters.has(id)}
            className={cn(
              "orbit-filter",
              `orbit-filter--${getDecisionConfig(id).tone}`,
              activeFilters.has(id) && "is-active"
            )}
          >
            {getDecisionConfig(id).label}
            <span dir="ltr">{decisionCounts[id] || 0}</span>
          </button>
        ))}
        <i className="orbit-filters__separator" aria-hidden />
        {TOPIC_CHIPS.map((chip) => (
          <button
            type="button"
            key={chip.id}
            onClick={() => onToggle(chip.id)}
            aria-pressed={activeFilters.has(chip.id)}
            className={cn("orbit-filter", activeFilters.has(chip.id) && "is-active")}
          >
            {chip.label}
          </button>
        ))}
      </div>
      <div className="orbit-filters__result" aria-live="polite">
        {filtered ? (
          <>
            <span dir="ltr">{shownCount}</span> תוצאות
            <button type="button" onClick={onReset} aria-label="נקה את כל המסננים">
              <RotateCcw size={13} aria-hidden />
            </button>
          </>
        ) : (
          "הדירוג המלא"
        )}
      </div>
    </div>
  );
}

function QueueSignal({ decision }) {
  const config = getDecisionConfig(decision);
  return (
    <span
      className={cn("orbit-queue-signal", `orbit-queue-signal--${config.tone}`)}
      aria-label={config.label}
    >
      <i aria-hidden />
      {config.label}
    </span>
  );
}

function OrbitQueueStory({ item, index, onFocus, localScoredArticles, reduce }) {
  const isCluster = item.type === "cluster";
  const reports = orbitStoryReports(item, localScoredArticles);
  const hasClusterField = orbitHasMultiSourceField(item, reports);
  const sourceCount = orbitUniqueSourceCount(reports);
  const title = orbitStoryTitle(item);
  const source = orbitStorySourceLine(item, reports);
  const publishedAt = orbitStoryTimestamp(item, reports);
  const kicker = buildKicker(item);
  const feedbackId = orbitFeedbackArticleId(item, reports);
  const config = getDecisionConfig(item.score?.decision);
  const { queueDensity, queueRail, queueMuted } = config.orbit;
  const showSubtitle = queueDensity !== "compact" && Boolean(item.subtitle);
  const articleUrl =
    (isCluster
      ? reports.find((report) => report.articleId === item.primaryArticleId)?.url ??
        reports[0]?.url
      : item.url) ?? null;

  return (
    <motion.article
      {...queueEnterMotion(reduce)}
      transition={queueEnterTransition(index, reduce)}
      className={cn(
        "orbit-queue-story",
        `orbit-queue-story--${config.tone}`,
        `orbit-queue-story--${queueDensity}`,
        queueRail && "orbit-queue-story--railed",
        queueMuted && "orbit-queue-story--muted"
      )}
    >
      <button type="button" onClick={onFocus} className="orbit-queue-story__main">
        <div className="orbit-queue-story__topline">
          <QueueSignal decision={item.score?.decision} />
          <span>{kicker || "סיפור בדירוג"}</span>
        </div>
        <h3>{title}</h3>
        {showSubtitle && <p>{item.subtitle}</p>}
        <div className="orbit-queue-story__meta">
          <SourceMeta
            source={source}
            publishedAt={publishedAt}
            extraSourceCount={Math.max(sourceCount - 1, 0)}
          />
          <span className="orbit-queue-story__focus">
            למרכז
            <ChevronLeft size={14} aria-hidden />
          </span>
        </div>
      </button>

      <div className="orbit-queue-story__actions">
        {hasClusterField && (
          <span className="orbit-queue-story__cluster">
            <Layers3 size={13} aria-hidden />
            {sourceCount} מקורות
          </span>
        )}
        <span className="orbit-queue-story__action-buttons">
          {feedbackId && <FeedbackControls key={feedbackId} articleId={feedbackId} />}
          {!hasClusterField && articleUrl && (
            <a
              href={articleUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="פתח את הדיווח"
              title="פתח את הדיווח"
            >
              <ArrowUpLeft size={15} aria-hidden />
            </a>
          )}
        </span>
      </div>
    </motion.article>
  );
}

export default function OrbitFeedView({
  items,
  localScoredArticles,
  profileName,
  scanned,
  decisionCounts,
  activeFilters,
  onToggleFilter,
  onResetFilters,
}) {
  const reduce = useReducedMotion();
  const [selectedFocusId, setSelectedFocusId] = useState(null);
  const [expandedStoryId, setExpandedStoryId] = useState(null);
  const [queuePages, setQueuePages] = useState(1);

  const resolvedFocus = useMemo(
    () => resolveOrbitFocus(items, selectedFocusId),
    [items, selectedFocusId]
  );
  const focusItem = resolvedFocus.item;
  const queueItems = useMemo(
    () => orbitQueueItems(items, focusItem),
    [focusItem, items]
  );
  // Render a bounded slice: the number of animating, laid-out nodes must not
  // track the size of the feed. See orbitQueueMotion.
  const page = queuePage(queueItems.length, queuePages);
  const visibleQueueItems = queueItems.slice(0, page.visible);
  const activeStoryId = orbitStoryId(focusItem);
  const expanded =
    Boolean(activeStoryId) && expandedStoryId === activeStoryId;
  const previousActiveStoryId = useRef(activeStoryId);

  useEffect(() => {
    if (selectedFocusId && !resolvedFocus.isPinned) {
      setSelectedFocusId(null);
      setExpandedStoryId(null);
    }
  }, [resolvedFocus.isPinned, selectedFocusId]);

  // A new filter selection is a new list: start it from the first page.
  useEffect(() => {
    setQueuePages(1);
  }, [activeFilters]);

  useEffect(() => {
    const previousStoryId = previousActiveStoryId.current;
    previousActiveStoryId.current = activeStoryId;
    if (!previousStoryId || previousStoryId === activeStoryId) return;

    const shouldRestoreFocus = expandedStoryId === previousStoryId;
    if (expandedStoryId) setExpandedStoryId(null);
    if (!shouldRestoreFocus) return;

    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const cores = document.querySelectorAll(".orbit-field .orbit-core");
        const core = cores[cores.length - 1];
        if (core instanceof HTMLElement) core.focus({ preventScroll: true });
      });
    });
  }, [activeStoryId, expandedStoryId]);

  const focusStory = (item) => {
    setExpandedStoryId(null);
    setSelectedFocusId(orbitStoryId(item));
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const field = document.querySelector(".orbit-field");
        const cores = field?.querySelectorAll(".orbit-core");
        const core = cores?.[cores.length - 1];
        if (core instanceof HTMLElement) core.focus({ preventScroll: true });
        if (!window.matchMedia("(min-width: 1200px)").matches) {
          field?.scrollIntoView({
            behavior: reduce ? "auto" : "smooth",
            block: "start",
          });
        }
      });
    });
  };

  const openCluster = () => {
    setExpandedStoryId(activeStoryId);
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const field = document.querySelector(".orbit-field");
        const closeAction = field?.querySelector(".orbit-close-action");
        if (closeAction instanceof HTMLElement) {
          closeAction.focus({ preventScroll: true });
        }
        field?.scrollIntoView({
          behavior: reduce ? "auto" : "smooth",
          block: "start",
        });
      });
    });
  };

  const closeCluster = () => {
    setExpandedStoryId(null);
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const primaryAction = document.querySelector(
          ".orbit-field .orbit-primary-action"
        );
        if (primaryAction instanceof HTMLElement) {
          primaryAction.focus({ preventScroll: true });
        }
      });
    });
  };

  const urgentCount = decisionCounts.push;
  const totalCount = Object.values(decisionCounts).reduce(
    (sum, count) => sum + count,
    0
  );

  return (
    <div className="orbit-feed-view">
      <OrbitFeedHeading
        profileName={profileName}
        total={totalCount}
        scanned={scanned}
        urgentCount={urgentCount}
      />

      <OrbitFilters
        activeFilters={activeFilters}
        decisionCounts={decisionCounts}
        shownCount={items.length}
        totalCount={totalCount}
        onToggle={onToggleFilter}
        onReset={onResetFilters}
      />

      {items.length === 0 ? (
        <div className="orbit-filter-empty">
          <EmptyState
            icon={SlidersHorizontal}
            title="אין סיפורים שמתאימים לכיוון הזה"
            hint="אפשר לשנות את המסננים או לחזור למסלול המלא."
            action={
              <button type="button" onClick={onResetFilters} className="orbit-primary-action">
                חזרה למסלול המלא
              </button>
            }
          />
        </div>
      ) : (
        <div className={cn("orbit-feed-layout", expanded && "is-expanded")}>
          <OrbitStoryField
            item={focusItem}
            localScoredArticles={localScoredArticles}
            isPinned={resolvedFocus.isPinned}
            expanded={expanded}
            onExpand={openCluster}
            onClose={closeCluster}
          />

          <aside className="orbit-queue" aria-label="המשך המסלול">
            <div className="orbit-queue__heading">
              <div>
                <span>המשך המסלול</span>
                <h2>עוד בדירוג שלך</h2>
              </div>
              <strong dir="ltr">
                {page.hasMore ? `${page.visible}/${queueItems.length}` : queueItems.length}
              </strong>
            </div>

            {queueItems.length > 0 ? (
              <>
                {/* No AnimatePresence: a card that stops matching the filter
                    unmounts immediately instead of animating out. */}
                <div className="orbit-queue__list">
                  {visibleQueueItems.map((item, index) => (
                    <OrbitQueueStory
                      key={orbitStoryId(item)}
                      item={item}
                      index={index}
                      onFocus={() => focusStory(item)}
                      localScoredArticles={localScoredArticles}
                      reduce={reduce}
                    />
                  ))}
                </div>
                {page.hasMore && (
                  <button
                    type="button"
                    className="orbit-queue__more"
                    onClick={() => setQueuePages((pages) => pages + 1)}
                  >
                    עוד <span dir="ltr">{page.remaining}</span> במסלול
                  </button>
                )}
              </>
            ) : (
              <p className="orbit-queue__quiet">זה הסיפור היחיד במסלול כרגע.</p>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
