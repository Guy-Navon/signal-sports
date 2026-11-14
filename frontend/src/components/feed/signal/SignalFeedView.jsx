import React, { useContext, useEffect, useId, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import SignalStrength from "@/components/signal-ui/SignalStrength";
import MastheadSlot, { MastheadSlotContext } from "@/components/shell/MastheadSlot";
import FeedbackControls from "@/components/feed/FeedbackControls";
import ResultsStrip from "./ResultsStrip";
import FeedFilterBar from "./FeedFilterBar";
import { useArticleOpened, useEngineTraceVisible } from "@/context/appContextCore";
import { getDecisionConfig } from "@/components/feed/decisionConfig";
import { deskVoiceView } from "@/components/feed/deskVoiceModel";
import { filterFeedItems, itemSourceFilterIds, leagueFilterId, visibleCount } from "@/components/feed/feedFilters";
import { queuePage } from "@/components/feed/queueMotion";
import {
  feedbackArticleId,
  storyId,
  storyReports,
  storySourceLine,
  storyTimestamp,
  storyTitle,
  feedSurface,
} from "@/components/feed/storyModel";
import {
  feedSummary,
  filterEmptyMessage,
  isFreshStory,
  latestStories,
  leaguePills,
  showMoreFocusIndex,
  splitFeedSections,
} from "./feedLayoutModel";
import {
  LOAD_SEQUENCE,
  SETTLED_SEQUENCE,
  enterStyle,
  loadSettleMs,
  nextArrivals,
  pageStaggerIndex,
  storyIdSet,
} from "./feedMotionModel";
import {
  relativeTimeHe,
  storyLink,
  storySources,
  titleDirection,
  unbreakableHebrewPrefixes,
} from "./signalStoryModel";
import "@/components/signal-ui/signal-ui.css";
import "./signal-feed.css";
import "./feed-filters.css";

// The new consumer feed (#464, docs/FRONTEND_DESIGN_SYSTEM.md Part B): summary
// line, league pills (the filters), a lead block only when there is a push, the
// important row, then the stream of compact three-line rows. Placement comes
// from feedLayoutModel; nothing here ranks, scores or invents a level.

const TICK_MS = 60_000;

/** Relative times stay current without a reload. */
function useNow(fixedNowMs) {
  const [now, setNow] = useState(() => fixedNowMs ?? Date.now());
  useEffect(() => {
    if (fixedNowMs != null) {
      setNow(fixedNowMs);
      return undefined;
    }
    const id = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(id);
  }, [fixedNowMs]);
  return now;
}

/**
 * The first-load choreography builds the page top to bottom (LOAD_SEQUENCE);
 * once it has played, every base is 0, so a filter change, "show more" or a
 * new story enters at once. The motion is CSS and stops under reduced motion.
 */
function useEnterSequence() {
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setSettled(true), loadSettleMs());
    return () => clearTimeout(id);
  }, []);
  return settled ? SETTLED_SEQUENCE : LOAD_SEQUENCE;
}

/**
 * Stories that arrived with the latest refresh (nextArrivals). Adjusted while
 * rendering when the list changes, so the new rows mount already marked.
 */
function useArrivals(items) {
  const [track, setTrack] = useState(() => ({
    items,
    ids: storyIdSet(items),
    arrivals: new Set(),
  }));
  if (track.items === items) return track.arrivals;
  const ids = storyIdSet(items);
  const next = {
    items,
    ids,
    arrivals: nextArrivals({ previousIds: track.ids, currentIds: ids, previousArrivals: track.arrivals }),
  };
  setTrack(next);
  return next.arrivals;
}

/** A story that came in with the latest refresh: a word, not only motion (A6). */
function NewMark({ show }) {
  return show ? <span className="sg-new">חדש</span> : null;
}

/** Everything a row needs about one story, from the shared story models. */
function useStory(item, localScoredArticles) {
  return useMemo(() => {
    const reports = storyReports(item, localScoredArticles);
    return {
      id: storyId(item),
      title: unbreakableHebrewPrefixes(storyTitle(item)),
      titleDir: titleDirection(item),
      url: storyLink(item, reports),
      source: storySourceLine(item, reports),
      sources: storySources(item, reports),
      timestamp: storyTimestamp(item, reports),
      feedbackId: feedbackArticleId(item, reports),
      decision: item.score?.decision,
    };
  }, [item, localScoredArticles]);
}

function useSurface(readOnly) {
  return feedSurface({ readOnly, traceAllowed: useEngineTraceVisible() });
}

function StoryLink({ story, className = "", linkRef = undefined, children = null }) {
  const noteArticleOpened = useArticleOpened();
  if (!story.url) return <span className={className}>{children}</span>;
  return (
    <a
      ref={linkRef}
      href={story.url}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
      onClick={() => noteArticleOpened(story.feedbackId)}
    >
      {children}
    </a>
  );
}

function Headline({ as = "h3", story, className = "", linkRef = undefined }) {
  const Tag = /** @type {"h2" | "h3"} */ (as);
  return (
    <Tag className={className} dir={story.titleDir}>
      <StoryLink story={story} className="sg-headline-link" linkRef={linkRef}>
        {story.title}
      </StoryLink>
    </Tag>
  );
}

/** "למה אצלך:" + the reader's reason, for every consumer role.
 * @param {{ item: any, showTrace?: boolean, className?: string, children?: React.ReactNode }} props
 */
function WhyLine({ item, className = "", children = null }) {
  const view = deskVoiceView({
    reason: item.score?.reasonHe,
  });
  if (!view && !children) return null;
  return (
    <p className={cn("sg-why", className)}>
      {children}
      {view && (
        <>
          <b>למה אצלך: </b>
          {view.text}
        </>
      )}
    </p>
  );
}

function SourceNames({ story }) {
  const { sources } = story;
  if (!sources.multi) return <bdi dir="auto">{story.source}</bdi>;
  return (
    <>
      <span className="sg-num">{sources.count}</span> מקורות:{" "}
      {/* Each member source opens its own report, so a cluster's sources stay
          reachable outside the stream too. */}
      <span className="sg-sources" role="list" aria-label="מקורות הסיפור">
        {sources.reports.map((report, index) => (
          <span role="listitem" key={report.articleId ?? report.sourceDisplayName}>
            {index > 0 && <Dot />}
            <MemberLink report={report} className="sg-source-link">
              <bdi dir="auto">{report.sourceDisplayName}</bdi>
            </MemberLink>
          </span>
        ))}
      </span>
    </>
  );
}

function Time({ value, now }) {
  const label = relativeTimeHe(value, now);
  if (!label) return null;
  return <time dateTime={value}>{label}</time>;
}

function Dot() {
  return <span aria-hidden="true"> · </span>;
}

function Feedback({ story, surface, className = "" }) {
  if (!surface.showFeedback || !story.feedbackId) return null;
  return (
    <span className={cn("sg-acts", className)}>
      <FeedbackControls key={story.feedbackId} articleId={story.feedbackId} variant="text" />
    </span>
  );
}

function SummaryLine({ items }) {
  const summary = feedSummary(items);
  return (
    <p className="sg-summary">
      {/* Keyed by value: a changed count ticks in (#467). */}
      <b key={`s${summary.stories}`} className="sg-num sg-tick" dir="ltr">{summary.stories}</b>{" "}
      {summary.storiesPhrase}
      <Dot />
      <b key={`i${summary.important}`} className="sg-num sg-tick" dir="ltr">{summary.important}</b>{" "}
      {summary.importantPhrase}
    </p>
  );
}

function LeadStory({ item, localScoredArticles, now, readOnly, enterBase }) {
  const story = useStory(item, localScoredArticles);
  const surface = useSurface(readOnly);
  return (
    <section
      className="sg-lead"
      aria-label={getDecisionConfig("push").label}
      data-decision={story.decision}
      data-league={leagueFilterId(item)}
      data-sources={JSON.stringify(itemSourceFilterIds(item))}
      style={enterStyle(0, enterBase)}
    >
      <div className="sg-lead__deco" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
      <span className="sg-lead__label">
        <span className="sg-lead__dot" aria-hidden="true" />
        {getDecisionConfig("push").label}
      </span>
      <Headline as="h2" story={story} className="sg-lead__title sg-lead-title" />
      <div className="sg-lead__row">
        {item.subtitle ? <p className="sg-lead__dek">{item.subtitle}</p> : <span />}
        <WhyLine item={item} showTrace={surface.showTrace} className="sg-lead__why" />
        <div className="sg-lead__meta">
          <span>
            <SourceNames story={story} />
            {story.timestamp && <Dot />}
            <Time value={story.timestamp} now={now} />
          </span>
          {story.url && (
            <StoryLink story={story} className="sg-lead__go">
              לכתבה
            </StoryLink>
          )}
          <Feedback story={story} surface={surface} className="sg-acts--slab" />
        </div>
      </div>
    </section>
  );
}

function leagueLabelOf(item, pillLabels) {
  return pillLabels.get(leagueFilterId(item)) ?? null;
}

function ImportantStory({ item, localScoredArticles, now, readOnly, league, arrived, style }) {
  const story = useStory(item, localScoredArticles);
  const surface = useSurface(readOnly);
  return (
    <article
      className="sg-important__item"
      data-decision={story.decision}
      data-league={leagueFilterId(item)}
      data-sources={JSON.stringify(itemSourceFilterIds(item))}
      data-arrived={arrived || undefined}
      style={style}
    >
      <span className="sg-important__tags">
        <span className="sg-tag">
          <SignalStrength decision={story.decision} />
          {league && <bdi dir="auto">{league}</bdi>}
        </span>
        <NewMark show={arrived} />
      </span>
      <Headline story={story} className="sg-important__title" />
      <p className="sg-meta">
        <SourceNames story={story} />
        {story.timestamp && <Dot />}
        <Time value={story.timestamp} now={now} />
      </p>
      <Feedback story={story} surface={surface} className="sg-acts--quiet" />
    </article>
  );
}

function ClusterMembers({ story, now, id }) {
  return (
    <ul className="sg-members" id={id} aria-label="מקורות הסיפור">
      {story.sources.reports.map((report, index) => (
        <li key={report.articleId ?? report.sourceDisplayName} style={enterStyle(index)}>
          <MemberLink report={report}>
            <b><bdi dir="auto">{report.sourceDisplayName}</bdi></b>
            {report.publishedAt && <Dot />}
            <Time value={report.publishedAt} now={now} />
            {report.title && (
              <span className="sg-members__title">{report.title}</span>
            )}
          </MemberLink>
        </li>
      ))}
    </ul>
  );
}

function MemberLink({ report, className = "sg-members__item", children = null }) {
  const noteArticleOpened = useArticleOpened();
  if (!report.url) return <span className={className}>{children}</span>;
  return (
    <a
      className={className}
      href={report.url}
      target="_blank"
      rel="noopener noreferrer"
      onClick={() => noteArticleOpened(report.articleId)}
    >
      {children}
    </a>
  );
}

function StreamRow({
  item,
  localScoredArticles,
  now,
  readOnly,
  league,
  focusOnMount,
  onFocused,
  arrived,
  style,
}) {
  const story = useStory(item, localScoredArticles);
  const surface = useSurface(readOnly);
  const [open, setOpen] = useState(false);
  const membersId = useId();
  const headlineRef = useRef(null);

  // Ref-based focus from inside the row that owns the element (A6): after
  // "show more", the first new row focuses its own headline once mounted.
  useEffect(() => {
    if (!focusOnMount) return;
    headlineRef.current?.focus({ preventScroll: false });
    onFocused?.();
  }, [focusOnMount, onFocused]);

  return (
    <article
      className="sg-row"
      data-decision={story.decision}
      data-league={leagueFilterId(item)}
      data-sources={JSON.stringify(itemSourceFilterIds(item))}
      data-arrived={arrived || undefined}
      style={style}
    >
      <div className="sg-row__by">
        <NewMark show={arrived} />
        <SignalStrength decision={story.decision} />
        <span className="sg-row__src">
          <bdi dir="auto">{story.source}</bdi>
          {story.timestamp && <Dot />}
          <Time value={story.timestamp} now={now} />
          {league && (
            <>
              <Dot />
              <bdi dir="auto">{league}</bdi>
            </>
          )}
        </span>
      </div>
      <Feedback story={story} surface={surface} className="sg-row__acts" />
      <Headline story={story} className="sg-row__title" linkRef={headlineRef} />
      <WhyLine item={item} showTrace={surface.showTrace} className="sg-row__why">
        {story.sources.multi && (
          <button
            type="button"
            className="sg-badge"
            aria-expanded={open}
            aria-controls={membersId}
            onClick={() => setOpen((value) => !value)}
          >
            <span className="sg-num">{story.sources.count}</span> מקורות
            <ChevronDown size={12} aria-hidden="true" className="sg-badge__chev" />
          </button>
        )}
      </WhyLine>
      {story.sources.multi && open && (
        <ClusterMembers story={story} now={now} id={membersId} />
      )}
    </article>
  );
}

/**
 * A bounded list (A5): one page of QUEUE_PAGE_SIZE rows, then "show more".
 * Removal is never animated: a row that leaves unmounts at once. Entering rows
 * stagger, capped and restarted on each page (feedMotionModel).
 */
function useStoryList({ items, renderRow, moreLabel }) {
  const [pages, setPages] = useState(1);
  const [focusIndex, setFocusIndex] = useState(null);
  const page = queuePage(items.length, pages);
  const visible = items.slice(0, page.visible);

  const showMore = () => {
    const next = queuePage(items.length, pages + 1);
    setFocusIndex(showMoreFocusIndex(page.visible, next.visible));
    setPages(pages + 1);
  };

  return {
    page,
    body: (
      <>
        {visible.map((item, index) =>
          renderRow(item, index === focusIndex, () => setFocusIndex(null), pageStaggerIndex(index))
        )}
      </>
    ),
    more: page.hasMore ? (
      <button type="button" className="sg-more" onClick={showMore}>
        {moreLabel(page.remaining)}
      </button>
    ) : null,
  };
}

function StreamSection({ items, localScoredArticles, now, readOnly, pillLabels, arrivals, enterBase }) {
  const list = useStoryList({
    items,
    moreLabel: (remaining) => (
      <>
        ועוד <span className="sg-num" dir="ltr">{remaining}</span> סיפורים בפיד
      </>
    ),
    renderRow: (item, focusOnMount, onFocused, staggerIndex) => (
      <StreamRow
        key={storyId(item)}
        item={item}
        localScoredArticles={localScoredArticles}
        now={now}
        readOnly={readOnly}
        league={leagueLabelOf(item, pillLabels)}
        focusOnMount={focusOnMount}
        onFocused={onFocused}
        arrived={arrivals.has(storyId(item))}
        style={enterStyle(staggerIndex, enterBase)}
      />
    ),
  });
  return (
    <section
      className="sg-stream-section"
      aria-labelledby="sg-stream-heading"
      style={enterStyle(0, enterBase)}
    >
      <h2 className="sg-sech" id="sg-stream-heading">
        עוד בפיד שלך <span>מדורג לפי מה שחשוב לך</span>
        {list.page.hasMore && (
          <span className="sg-sech__count sg-num" dir="ltr">
            {`${list.page.visible}/${items.length}`}
          </span>
        )}
      </h2>
      <div className="sg-stream">{list.body}</div>
      {list.more}
    </section>
  );
}

function BriefRow({ item, localScoredArticles, now, readOnly, focusOnMount, onFocused, style }) {
  const story = useStory(item, localScoredArticles);
  const surface = useSurface(readOnly);
  const headlineRef = useRef(null);
  useEffect(() => {
    if (!focusOnMount) return;
    headlineRef.current?.focus();
    onFocused?.();
  }, [focusOnMount, onFocused]);
  return (
    <li
      className="sg-box__item sg-brief__item"
      data-decision={story.decision}
      data-league={leagueFilterId(item)}
      data-sources={JSON.stringify(itemSourceFilterIds(item))}
      style={style}
    >
      <Headline story={story} className="sg-box__title sg-brief__title" linkRef={headlineRef} />
      <div className="sg-box__meta sg-brief__meta">
        <span>
          <Time value={story.timestamp} now={now} />
          {story.timestamp && <Dot />}
          <SourceNames story={story} />
        </span>
        <Feedback story={story} surface={surface} className="sg-acts--quiet" />
      </div>
    </li>
  );
}

function LatestRow({ item, localScoredArticles, now, arrived, style }) {
  const story = useStory(item, localScoredArticles);
  const fresh = isFreshStory(story.timestamp, now);
  return (
    <li
      className="sg-box__item sg-latest__item"
      data-decision={story.decision}
      data-league={leagueFilterId(item)}
      data-sources={JSON.stringify(itemSourceFilterIds(item))}
      data-fresh={fresh || undefined}
      data-arrived={arrived || undefined}
      style={style}
    >
      <Headline story={story} className="sg-box__title" />
      <span className="sg-box__meta">
        <SignalStrength decision={story.decision} />
        {/* Under an hour old: a pulsing --hot dot (a non-text mark) and the time
            in bold ink. Small --hot text on white fails contrast (B2). */}
        {fresh && <span className="sg-fresh-dot" aria-hidden="true" />}
        <span className={fresh ? "sg-latest__fresh" : undefined}>
          <Time value={story.timestamp} now={now} />
        </span>
        <Dot />
        <bdi dir="auto">{story.source}</bdi>
      </span>
    </li>
  );
}

// "אחרונים": the newest visible non-low stories (latestStories). A view of the
// filtered list only: the stream keeps its ranked order, and a story may stand
// in both places, as in the approved mock. No feedback here: every story in it
// carries its actions where it is placed (lead, important row, stream).
function LatestSection({ items, localScoredArticles, now, arrivals, enterBase }) {
  if (items.length === 0) return null;
  return (
    <section className="sg-box sg-latest" aria-labelledby="sg-latest-heading">
      <h2 className="sg-box__heading" id="sg-latest-heading">אחרונים</h2>
      <ul>
        {items.map((item, index) => (
          <LatestRow
            key={storyId(item)}
            item={item}
            localScoredArticles={localScoredArticles}
            now={now}
            arrived={arrivals.has(storyId(item))}
            style={enterStyle(index, enterBase)}
          />
        ))}
      </ul>
    </section>
  );
}

// "בקצרה": the low_feed stories, in the side column (#465), bounded like the stream.
function BriefSection({ items, localScoredArticles, now, readOnly, enterBase }) {
  const list = useStoryList({
    items,
    moreLabel: (remaining) => (
      <>
        ועוד <span className="sg-num" dir="ltr">{remaining}</span> בקצרה
      </>
    ),
    renderRow: (item, focusOnMount, onFocused, staggerIndex) => (
      <BriefRow
        key={storyId(item)}
        item={item}
        localScoredArticles={localScoredArticles}
        now={now}
        readOnly={readOnly}
        focusOnMount={focusOnMount}
        onFocused={onFocused}
        style={enterStyle(staggerIndex, enterBase)}
      />
    ),
  });
  return (
    <section className="sg-box sg-brief" aria-labelledby="sg-brief-heading">
      <h2 className="sg-box__heading sg-brief__heading" id="sg-brief-heading">בקצרה</h2>
      <ul>{list.body}</ul>
      {list.more}
    </section>
  );
}

const defaultFilterBar = (bar) => <FeedFilterBar {...bar} />;

/**
 * items: the visible, prepared stories (prepareFeedItems), unfiltered.
 * localScoredArticles: the local/mock catalogue for cluster members; [] in backend mode.
 * readOnly: the public demo; no feedback controls, no engine trace.
 * status: a quiet line above the summary (FeedFreshness, the demo banner).
 * nowMs: a fixed "now" for relative times (lab snapshots); live otherwise.
 * ground: only for a standalone render; inside a parent scope it follows the parent.
 * filterBar: LAB SEAM ONLY (lab.html?page=filters, #483): renders a candidate
 *   filter bar in place of FeedFilterBar, with the same inputs. Product code
 *   never passes it.
 * @param {{
 *   items: any[],
 *   results?: any[],
 *   localScoredArticles?: any[],
 *   activeFilters: Set<string>,
 *   onToggleFilter: (id: string) => void,
 *   onResetFilters: () => void,
 *   readOnly?: boolean,
 *   status?: React.ReactNode,
 *   nowMs?: number,
 *   ground?: "soft" | "dark",
 *   filterBar?: (bar: any) => React.ReactNode,
 * }} props
 */
export default function SignalFeedView({
  items,
  results = [],
  localScoredArticles = [],
  activeFilters,
  onToggleFilter,
  onResetFilters,
  readOnly = false,
  status = null,
  nowMs,
  ground,
  filterBar = undefined,
}) {
  const now = useNow(nowMs);
  const sequence = useEnterSequence();
  const arrivals = useArrivals(items);
  const filtered = useMemo(() => filterFeedItems(items, activeFilters), [items, activeFilters]);
  const sections = useMemo(() => splitFeedSections(filtered), [filtered]);
  const latest = useMemo(
    () => latestStories(filtered, { localScoredArticles }),
    [filtered, localScoredArticles]
  );
  const pillLabels = useMemo(
    () => new Map(leaguePills(items).map((pill) => [pill.id, pill.label])),
    [items]
  );
  // A new filter selection is a new list: it starts again from its first page.
  const listKey = [...activeFilters].sort().join("|");
  const rowProps = { localScoredArticles, now, readOnly };
  const mastheadSlot = useContext(MastheadSlotContext);
  const head = (
    <>
      {status && <div className="sg-status">{status}</div>}
      <SummaryLine items={items} />
      {(filterBar ?? defaultFilterBar)({
        items,
        activeFilters,
        shown: visibleCount(filtered),
        onToggle: onToggleFilter,
        onReset: onResetFilters,
        enterBase: sequence.pills,
      })}
    </>
  );

  return (
    <div className="signal-ui sg-feed" data-ground={ground}>
      <h1 className="sr-only">הפיד שלך</h1>
      {/* New stories are marked with a word and a glow; this says it once. */}
      <p className="sr-only" role="status">
        {arrivals.size === 1
          ? "סיפור חדש אחד נוסף לפיד"
          : arrivals.size > 1
            ? `${arrivals.size} סיפורים חדשים נוספו לפיד`
            : ""}
      </p>
      {/* Inside the consumer shell (#463) the summary line and pills sit under
          the wordmark, through its masthead slot; on their own (the lab, the
          demo until #469) they open the view. */}
      {mastheadSlot ? (
        <MastheadSlot>
          <div className="sg-feed__head sg-feed__head--slot">{head}</div>
        </MastheadSlot>
      ) : (
        <header className="sg-feed__head sg-in">{head}</header>
      )}

      {filtered.length === 0 ? (
        <div className="sg-in sg-filter-empty">
          <p>{filterEmptyMessage(activeFilters)}</p>
          <button type="button" className="sg-more" onClick={onResetFilters}>
            הצג את כל הפיד
          </button>
        </div>
      ) : (
        <>
          <div className="sg-in">
            {/* Keyed by story: a new lead plays its entrance again. */}
            {sections.lead && (
              <LeadStory
                key={storyId(sections.lead)}
                item={sections.lead}
                enterBase={sequence.lead}
                {...rowProps}
              />
            )}

            {sections.important.length > 0 && (
              <section className="sg-important" aria-label="חשובים">
                {sections.important.map((item, index) => (
                  <ImportantStory
                    key={storyId(item)}
                    item={item}
                    league={leagueLabelOf(item, pillLabels)}
                    arrived={arrivals.has(storyId(item))}
                    style={enterStyle(index, sequence.important)}
                    {...rowProps}
                  />
                ))}
              </section>
            )}

            <ResultsStrip results={results} nowMs={now} enterBaseMs={sequence.results} />
          </div>

          {(sections.stream.length > 0 || sections.brief.length > 0 || latest.length > 0) && (
            <div className="sg-band">
              <div className="sg-in sg-cols">
                {sections.stream.length > 0 && (
                  <div className="sg-main">
                    <StreamSection
                      key={`stream-${listKey}`}
                      items={sections.stream}
                      pillLabels={pillLabels}
                      arrivals={arrivals}
                      enterBase={sequence.stream}
                      {...rowProps}
                    />
                  </div>
                )}
                {/* The side column (B11): sticky beside the stream on desktop; on
                    a phone it follows the stream (#465). Same filtered set. */}
                {(latest.length > 0 || sections.brief.length > 0) && (
                  <aside
                    className="sg-side"
                    aria-label="אחרונים ובקצרה"
                    style={enterStyle(0, sequence.side)}
                  >
                    <LatestSection
                      items={latest}
                      arrivals={arrivals}
                      enterBase={sequence.side}
                      {...rowProps}
                    />
                    {sections.brief.length > 0 && (
                      <BriefSection
                        key={`brief-${listKey}`}
                        items={sections.brief}
                        enterBase={sequence.side}
                        {...rowProps}
                      />
                    )}
                  </aside>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
