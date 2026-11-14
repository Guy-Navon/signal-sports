import React, { useContext, useEffect, useId, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import SignalStrength from "@/components/signal-ui/SignalStrength";
import MastheadSlot, { MastheadSlotContext } from "@/components/shell/MastheadSlot";
import FeedbackControls from "@/components/feed/FeedbackControls";
import ResultsStrip from "./ResultsStrip";
import { useArticleOpened, useEngineTraceVisible } from "@/context/appContextCore";
import { getDecisionConfig } from "@/components/feed/decisionConfig";
import { deskVoiceView } from "@/components/feed/deskVoiceModel";
import { filterFeedItems, leagueFilterId } from "@/components/feed/feedFilters";
import { queuePage } from "@/components/feed/orbit/orbitQueueMotion";
import {
  orbitFeedbackArticleId,
  orbitStoryId,
  orbitStoryReports,
  orbitStorySourceLine,
  orbitStoryTimestamp,
  orbitStoryTitle,
  orbitSurface,
} from "@/components/feed/orbit/orbitStoryModel";
import {
  feedSummary,
  leaguePills,
  showMoreFocusIndex,
  splitFeedSections,
} from "./feedLayoutModel";
import {
  relativeTimeHe,
  storyLink,
  storySources,
  titleDirection,
  unbreakableHebrewPrefixes,
} from "./signalStoryModel";
import "@/components/signal-ui/signal-ui.css";
import "./signal-feed.css";

// The new consumer feed (#464, docs/FRONTEND_DESIGN_SYSTEM.md Part B): summary
// line, league pills (the filters), a lead block only when there is a push, the
// important row, then the stream of compact three-line rows. Placement comes
// from feedLayoutModel; nothing here ranks, scores or invents a level.

const TICK_MS = 60_000;
const PILL_TINTS = 4;

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

/** Everything a row needs about one story, from the shared story models. */
function useStory(item, localScoredArticles) {
  return useMemo(() => {
    const reports = orbitStoryReports(item, localScoredArticles);
    return {
      id: orbitStoryId(item),
      title: unbreakableHebrewPrefixes(orbitStoryTitle(item)),
      titleDir: titleDirection(item),
      url: storyLink(item, reports),
      source: orbitStorySourceLine(item, reports),
      sources: storySources(item, reports),
      timestamp: orbitStoryTimestamp(item, reports),
      feedbackId: orbitFeedbackArticleId(item, reports),
      decision: item.score?.decision,
    };
  }, [item, localScoredArticles]);
}

function useSurface(readOnly) {
  return orbitSurface({ readOnly, traceAllowed: useEngineTraceVisible() });
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

/** "למה אצלך:" + the reader's reason (or, for ops, the engine line). */
function WhyLine({ item, showTrace, className = "", children = null }) {
  const view = deskVoiceView({
    showTrace,
    reason: item.score?.reasonHe,
    reasoning: item.score?.reasoning,
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
          reachable outside the stream too (Orbit exposed them in its field). */}
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
      <b className="sg-num" dir="ltr">{summary.stories}</b> {summary.storiesPhrase}
      <Dot />
      <b className="sg-num" dir="ltr">{summary.important}</b> {summary.importantPhrase}
    </p>
  );
}

function LeaguePills({ items, activeFilters, onToggle, onReset }) {
  const pills = useMemo(() => leaguePills(items), [items]);
  if (pills.length === 0) return null;
  const all = activeFilters.has("all");
  return (
    <div className="sg-pills" role="group" aria-label="סינון לפי ליגה">
      <button
        type="button"
        className="sg-pill sg-pill--all"
        aria-pressed={all}
        onClick={onReset}
      >
        <i className="sg-pill__mark" aria-hidden="true" />
        <b>הכול</b>
        <span className="sg-num" dir="ltr">{items.length}</span>
      </button>
      {pills.map((pill, index) => (
        <button
          type="button"
          key={pill.id}
          className="sg-pill"
          data-tint={(index % PILL_TINTS) + 1}
          data-filter={pill.id}
          aria-pressed={!all && activeFilters.has(pill.id)}
          onClick={() => onToggle(pill.id)}
        >
          <i className="sg-pill__mark" aria-hidden="true" />
          <b><bdi dir="auto">{pill.label}</bdi></b>
          <span className="sg-num" dir="ltr">{pill.count}</span>
        </button>
      ))}
    </div>
  );
}

function LeadStory({ item, localScoredArticles, now, readOnly }) {
  const story = useStory(item, localScoredArticles);
  const surface = useSurface(readOnly);
  return (
    <section
      className="sg-lead"
      aria-label={getDecisionConfig("push").label}
      data-decision={story.decision}
      data-league={leagueFilterId(item)}
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

function ImportantStory({ item, localScoredArticles, now, readOnly, league }) {
  const story = useStory(item, localScoredArticles);
  const surface = useSurface(readOnly);
  return (
    <article
      className="sg-important__item"
      data-decision={story.decision}
      data-league={leagueFilterId(item)}
    >
      <span className="sg-tag">
        <SignalStrength decision={story.decision} />
        {league && <bdi dir="auto">{league}</bdi>}
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
      {story.sources.reports.map((report) => (
        <li key={report.articleId ?? report.sourceDisplayName}>
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

function StreamRow({ item, localScoredArticles, now, readOnly, league, focusOnMount, onFocused }) {
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
    <article className="sg-row" data-decision={story.decision} data-league={leagueFilterId(item)}>
      <div className="sg-row__by">
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
 * Rows are plain elements: removal is never animated, and nothing staggers.
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
          renderRow(item, index === focusIndex, () => setFocusIndex(null))
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

function StreamSection({ items, localScoredArticles, now, readOnly, pillLabels }) {
  const list = useStoryList({
    items,
    moreLabel: (remaining) => (
      <>
        ועוד <span className="sg-num" dir="ltr">{remaining}</span> סיפורים בפיד
      </>
    ),
    renderRow: (item, focusOnMount, onFocused) => (
      <StreamRow
        key={orbitStoryId(item)}
        item={item}
        localScoredArticles={localScoredArticles}
        now={now}
        readOnly={readOnly}
        league={leagueLabelOf(item, pillLabels)}
        focusOnMount={focusOnMount}
        onFocused={onFocused}
      />
    ),
  });
  return (
    <section className="sg-stream-section" aria-labelledby="sg-stream-heading">
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

function BriefRow({ item, localScoredArticles, now, readOnly, focusOnMount, onFocused }) {
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
      className="sg-brief__item"
      data-decision={story.decision}
      data-league={leagueFilterId(item)}
    >
      <Headline story={story} className="sg-brief__title" linkRef={headlineRef} />
      <div className="sg-brief__meta">
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

// "בקצרה": the low_feed stories. They move into the side column with #465;
// until then they follow the stream so nothing visible today disappears.
function BriefSection({ items, localScoredArticles, now, readOnly }) {
  const list = useStoryList({
    items,
    moreLabel: (remaining) => (
      <>
        ועוד <span className="sg-num" dir="ltr">{remaining}</span> בקצרה
      </>
    ),
    renderRow: (item, focusOnMount, onFocused) => (
      <BriefRow
        key={orbitStoryId(item)}
        item={item}
        localScoredArticles={localScoredArticles}
        now={now}
        readOnly={readOnly}
        focusOnMount={focusOnMount}
        onFocused={onFocused}
      />
    ),
  });
  return (
    <section className="sg-brief" aria-labelledby="sg-brief-heading">
      <h2 className="sg-brief__heading" id="sg-brief-heading">בקצרה</h2>
      <ul>{list.body}</ul>
      {list.more}
    </section>
  );
}

/**
 * items: the visible, prepared stories (prepareFeedItems), unfiltered.
 * localScoredArticles: the local/mock catalogue for cluster members; [] in backend mode.
 * readOnly: the public demo; no feedback controls, no engine trace.
 * status: a quiet line above the summary (FeedFreshness, the demo banner).
 * nowMs: a fixed "now" for relative times (lab snapshots); live otherwise.
 * ground: only for a standalone render; inside a parent scope it follows the parent.
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
}) {
  const now = useNow(nowMs);
  const filtered = useMemo(() => filterFeedItems(items, activeFilters), [items, activeFilters]);
  const sections = useMemo(() => splitFeedSections(filtered), [filtered]);
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
      <LeaguePills
        items={items}
        activeFilters={activeFilters}
        onToggle={onToggleFilter}
        onReset={onResetFilters}
      />
    </>
  );

  return (
    <div className="signal-ui sg-feed" data-ground={ground}>
      <h1 className="sr-only">הפיד שלך</h1>
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
        <div className="sg-in sg-filter-empty" role="status">
          <p>אין סיפורים בליגות שבחרת.</p>
          <button type="button" className="sg-more" onClick={onResetFilters}>
            הצג את כל הפיד
          </button>
        </div>
      ) : (
        <>
          <div className="sg-in">
            {sections.lead && <LeadStory item={sections.lead} {...rowProps} />}

            {sections.important.length > 0 && (
              <section className="sg-important" aria-label="חשובים">
                {sections.important.map((item) => (
                  <ImportantStory
                    key={orbitStoryId(item)}
                    item={item}
                    league={leagueLabelOf(item, pillLabels)}
                    {...rowProps}
                  />
                ))}
              </section>
            )}

            <ResultsStrip results={results} nowMs={now} />
          </div>

          {(sections.stream.length > 0 || sections.brief.length > 0) && (
            <div className="sg-band">
              <div className="sg-in sg-cols">
                <div className="sg-main">
                  {sections.stream.length > 0 && (
                    <StreamSection
                      key={`stream-${listKey}`}
                      items={sections.stream}
                      pillLabels={pillLabels}
                      {...rowProps}
                    />
                  )}
                  {sections.brief.length > 0 && (
                    <BriefSection key={`brief-${listKey}`} items={sections.brief} {...rowProps} />
                  )}
                </div>
                {/* #465: <aside className="sg-side"> ("אחרונים" + "בקצרה", sticky on
                    desktop) goes here. .sg-cols becomes two columns when it exists. */}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
