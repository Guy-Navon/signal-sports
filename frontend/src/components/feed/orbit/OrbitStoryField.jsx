import React, { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowUpLeft,
  Clock3,
  Layers3,
  Radio,
  X,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { he } from "date-fns/locale";
import { cn } from "@/lib/utils";
import DeskVoice from "@/components/feed/DeskVoice";
import FeedbackControls from "@/components/feed/FeedbackControls";
import { buildKicker } from "@/components/feed/storyLabels";
import {
  orbitFeedbackArticleId,
  orbitHasMultiSourceField,
  orbitUniqueSourceCount,
  orbitStoryId,
  orbitStoryReports,
  orbitStorySourceLine,
  orbitStoryState,
  orbitStoryTimestamp,
  orbitStoryTitle,
  reportsChronologically,
  reportsWithPrimaryFirst,
  sourceInitial,
  detectNewSource,
  uniqueOrbitSourceReports,
} from "./orbitStoryModel";

function timeAgo(value) {
  if (!value) return "";
  try {
    return formatDistanceToNow(new Date(value), { addSuffix: true, locale: he });
  } catch {
    return value;
  }
}

function SourceIdentity({ report, compact = false }) {
  return (
    <>
      <span className="orbit-source-mark" aria-hidden>
        {sourceInitial(report.sourceDisplayName)}
      </span>
      <span className="orbit-source-copy">
        <bdi dir="auto">{report.sourceDisplayName}</bdi>
        <small>{compact ? "מקור בסיפור" : timeAgo(report.publishedAt)}</small>
      </span>
    </>
  );
}

function useSourceArrivals(storyId, reports) {
  const priorByStory = useRef(new Map());
  const [arrival, setArrival] = useState(null);

  useEffect(() => {
    if (!storyId) return undefined;

    const previousReports = priorByStory.current.get(storyId);
    priorByStory.current.set(storyId, reports);

    if (!previousReports) {
      setArrival(null);
      return undefined;
    }

    const joined = detectNewSource(previousReports, reports);
    if (!joined) {
      setArrival(null);
      return undefined;
    }

    setArrival(joined);
    const timer = window.setTimeout(() => setArrival(null), 3200);
    return () => window.clearTimeout(timer);
  }, [reports, storyId]);

  return arrival;
}

function FieldGeometry({ expanded = false }) {
  return (
    <svg
      aria-hidden
      className={cn("orbit-geometry", expanded && "orbit-geometry--expanded")}
      viewBox="0 0 1000 680"
      preserveAspectRatio="none"
    >
      <ellipse cx="500" cy="340" rx="428" ry="278" />
      <ellipse className="orbit-geometry__inner" cx="500" cy="340" rx="314" ry="202" />
      <path d="M80 454 C280 205 690 180 930 350" />
      {expanded && (
        <>
          <path className="orbit-geometry__join" d="M184 170 C308 220 370 270 430 320" />
          <path className="orbit-geometry__join" d="M820 165 C700 220 628 270 570 320" />
          <path className="orbit-geometry__join" d="M205 532 C330 455 380 410 438 365" />
          <path className="orbit-geometry__join" d="M795 535 C680 462 620 410 562 365" />
        </>
      )}
    </svg>
  );
}

function CompactSatellite({ report, index, isNew, reduce }) {
  const content = (
    <>
      <SourceIdentity report={report} compact />
      {isNew && <span className="orbit-source-new">חדש</span>}
    </>
  );

  const motionProps = reduce
    ? { initial: { opacity: 1 }, animate: { opacity: 1 }, exit: { opacity: 0 } }
    : {
        initial: { opacity: 0, scale: 0.9, y: 8 },
        animate: { opacity: 1, scale: 1, y: 0 },
        exit: { opacity: 0, scale: 0.95 },
        transition: { type: "spring", stiffness: 260, damping: 25, delay: index * 0.045 },
      };

  return (
    <motion.div
      layout={!reduce}
      {...motionProps}
      role="listitem"
      className={`orbit-satellite-slot orbit-satellite-slot--${index + 1}`}
    >
      {report.url ? (
        <a
          href={report.url}
          target="_blank"
          rel="noopener noreferrer"
          className={cn("orbit-satellite", isNew && "is-new")}
          aria-label={`פתח דיווח של ${report.sourceDisplayName}`}
        >
          {content}
        </a>
      ) : (
        <div className={cn("orbit-satellite", isNew && "is-new")}>{content}</div>
      )}
    </motion.div>
  );
}

function CompactCore({
  item,
  reports,
  state,
  onExpand,
  layoutId,
  fieldId,
  reduce,
}) {
  const isCluster = item.type === "cluster";
  const hasClusterField = orbitHasMultiSourceField(item, reports);
  const title = orbitStoryTitle(item);
  const sourceLine = orbitStorySourceLine(item, reports);
  const timestamp = orbitStoryTimestamp(item, reports);
  const kicker = buildKicker(item);
  const feedbackId = orbitFeedbackArticleId(item, reports);
  const articleUrl =
    (isCluster
      ? reports.find((report) => report.articleId === item.primaryArticleId)?.url ??
        reports[0]?.url
      : item.url) ?? null;
  const sourceCount = orbitUniqueSourceCount(reports);

  return (
    <motion.article
      layoutId={reduce ? undefined : layoutId}
      tabIndex={-1}
      className={cn("orbit-core", `orbit-core--${state.tone}`)}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 14, scale: 0.985 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.99 }}
      transition={
        reduce
          ? { duration: 0.12 }
          : { type: "spring", stiffness: 210, damping: 25, mass: 0.85 }
      }
    >
      <div className="orbit-core__topline">
        <span className="orbit-state-label">
          <i aria-hidden />
          {state.label}
        </span>
        <span>{kicker || "בדירוג האישי"}</span>
      </div>

      <h2>{title}</h2>

      {item.subtitle && <p className="orbit-core__summary">{item.subtitle}</p>}

      <DeskVoice
        reasoning={item.score?.reasoning}
        variant="full"
        className="orbit-core__reason"
      />

      <div className="orbit-core__meta">
        <span>
          <bdi dir="auto">{sourceLine}</bdi>
          {sourceCount > 1 && ` +${sourceCount - 1}`}
        </span>
        {timestamp && (
          <time dateTime={timestamp}>
            <Clock3 size={13} aria-hidden />
            {timeAgo(timestamp)}
          </time>
        )}
      </div>

      <div className="orbit-core__actions">
        {hasClusterField ? (
          <button
            type="button"
            onClick={onExpand}
            className="orbit-primary-action"
            aria-expanded={false}
            aria-controls={fieldId}
          >
            פתח את שדה הסיפור
            <Layers3 size={16} aria-hidden />
          </button>
        ) : articleUrl ? (
          <a
            href={articleUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="orbit-primary-action"
          >
            קרא את הדיווח
            <ArrowUpLeft size={16} aria-hidden />
          </a>
        ) : null}
        {feedbackId && (
          <FeedbackControls
            key={feedbackId}
            articleId={feedbackId}
            className="orbit-core__feedback"
          />
        )}
      </div>
    </motion.article>
  );
}

function ExpandedReport({ report, index, primaryId, newestId, isNew, reduce }) {
  const isPrimary = report.articleId === primaryId;
  const isNewest = report.articleId === newestId;
  const body = (
    <>
      <div className="orbit-report__heading">
        <SourceIdentity report={report} />
        <span className="orbit-report__sequence" dir="ltr">
          {String(index + 1).padStart(2, "0")}
        </span>
      </div>
      <div className="orbit-report__status">
        {isNew
          ? "מקור שהצטרף עכשיו"
          : isPrimary
            ? "הדיווח המוצג"
            : isNewest
              ? "העדכון האחרון"
              : "דיווח נוסף"}
      </div>
      <h3>{report.title || "דיווח נוסף על אותו אירוע"}</h3>
      {report.url && (
        <span className="orbit-report__link">
          לדיווח המקורי
          <ArrowUpLeft size={13} aria-hidden />
        </span>
      )}
    </>
  );

  const props = reduce
    ? { initial: { opacity: 1 }, animate: { opacity: 1 } }
    : {
        initial: { opacity: 0, scale: 0.96 },
        animate: { opacity: 1, scale: 1 },
        transition: { type: "spring", stiffness: 220, damping: 24, delay: index * 0.055 },
      };

  if (report.url) {
    return (
      <motion.a
        layout={!reduce}
        {...props}
        href={report.url}
        target="_blank"
        rel="noopener noreferrer"
        className={cn("orbit-report", isNew && "is-new")}
      >
        {body}
      </motion.a>
    );
  }

  return (
    <motion.article
      layout={!reduce}
      {...props}
      className={cn("orbit-report", isNew && "is-new")}
    >
      {body}
    </motion.article>
  );
}

function ExpandedCluster({
  item,
  reports,
  arrival,
  onClose,
  state,
  layoutId,
  fieldId,
  reduce,
}) {
  const chronological = reportsChronologically(reports);
  const sourceCount = orbitUniqueSourceCount(reports);
  const newestId = chronological.at(-1)?.articleId;
  const title = orbitStoryTitle(item);
  const feedbackId = orbitFeedbackArticleId(item, reports);

  return (
    <motion.div
      className={cn("orbit-cluster", chronological.length > 6 && "orbit-cluster--dense")}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: reduce ? 0.12 : 0.24 }}
    >
      <div className="orbit-cluster__heading">
        <div>
          <span className="orbit-cluster__eyebrow">
            <Radio size={13} aria-hidden />
            שדה סיפור · {sourceCount} מקורות גלויים · {chronological.length} דיווחים
          </span>
          <h2>
            {chronological.length} דיווחים מ־{sourceCount} מקורות. סיפור אחד.
          </h2>
          <p>כל מקור נשאר נפרד; הסדר מציג את רצף ההגעה לסיפור.</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="orbit-close-action"
          aria-expanded={true}
          aria-controls={fieldId}
        >
          <X size={16} aria-hidden />
          חזרה למסלול
        </button>
      </div>

      <div className="orbit-cluster__canvas">
        <FieldGeometry expanded />

        <motion.article
          layoutId={reduce ? undefined : layoutId}
          className={cn("orbit-cluster__core", `orbit-core--${state.tone}`)}
          transition={
            reduce
              ? { duration: 0.12 }
              : { type: "spring", stiffness: 190, damping: 24, mass: 0.9 }
          }
        >
          <span className="orbit-state-label">
            <i aria-hidden />
            {state.label}
          </span>
          <small>{chronological.length > 1 ? "כיסוי רב־מקורי" : "דיווח יחיד"}</small>
          <h3>{title}</h3>
          {item.subtitle && <p>{item.subtitle}</p>}
          <DeskVoice
            reasoning={item.score?.reasoning}
            variant="line"
            className="orbit-cluster__reason"
          />
          {feedbackId && (
            <FeedbackControls
              key={feedbackId}
              articleId={feedbackId}
              variant="text"
              className="orbit-cluster__feedback"
            />
          )}
        </motion.article>

        <div className="orbit-cluster__sources" role="list" aria-label="מקורות הסיפור">
          <AnimatePresence initial={false}>
            {chronological.map((report, index) => (
              <div role="listitem" key={report.articleId ?? `${report.source}-${index}`}>
                <ExpandedReport
                  report={report}
                  index={index}
                  primaryId={item.primaryArticleId}
                  newestId={newestId}
                  isNew={arrival?.articleId === report.articleId}
                  reduce={reduce}
                />
              </div>
            ))}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}

export default function OrbitStoryField({
  item,
  localScoredArticles,
  isPinned,
  expanded,
  onExpand,
  onClose,
}) {
  const reduce = useReducedMotion();
  const reports = useMemo(
    () => orbitStoryReports(item, localScoredArticles),
    [item, localScoredArticles]
  );
  const sourceReports = useMemo(
    () => uniqueOrbitSourceReports(reportsWithPrimaryFirst(item, reports)),
    [item, reports]
  );
  const compactReports = sourceReports.slice(0, 3);
  const sourceCount = sourceReports.length;
  const storyId = orbitStoryId(item);
  const state = orbitStoryState(item);
  const arrival = useSourceArrivals(storyId, reports);
  const layoutId = `orbit-story-core-${storyId}`;
  const fieldId = `orbit-story-field-${String(storyId).replace(/[^a-zA-Z0-9_-]/g, "-")}`;

  return (
    <section
      id={fieldId}
      className={cn(
        "orbit-field",
        expanded && "orbit-field--expanded",
        `orbit-field--${state.tone}`
      )}
      aria-label={
        expanded
          ? "שדה הסיפור המורחב"
          : isPinned
            ? "הסיפור שנבחר למוקד"
            : "הסיפור שמוביל כרגע"
      }
    >
      <div className="orbit-field__ambient" aria-hidden />

      <AnimatePresence initial={false}>
        {expanded ? (
          <ExpandedCluster
            key={`expanded-${storyId}`}
            item={item}
            reports={reports}
            arrival={arrival}
            onClose={onClose}
            state={state}
            layoutId={layoutId}
            fieldId={fieldId}
            reduce={reduce}
          />
        ) : (
          <motion.div
            key={`compact-${storyId}`}
            className="orbit-field__compact"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduce ? 0.12 : 0.2 }}
          >
            <div className="orbit-field__caption">
              <span>{isPinned ? "הסיפור שבחרת למוקד" : "הסיפור שמוביל כרגע"}</span>
              <strong>{sourceCount > 1 ? `${sourceCount} מקורות בסיפור` : "דיווח אחד"}</strong>
            </div>

            <FieldGeometry />

            <CompactCore
              item={item}
              reports={reports}
              state={state}
              onExpand={onExpand}
              layoutId={layoutId}
              fieldId={fieldId}
              reduce={reduce}
            />

            <div className="orbit-satellites" role="list" aria-label="מקורות הסיפור">
              <AnimatePresence initial={false}>
                {compactReports.map((report, index) => (
                  <CompactSatellite
                    key={report.articleId ?? `${report.source}-${index}`}
                    report={report}
                    index={index}
                    isNew={arrival?.articleId === report.articleId}
                    reduce={reduce}
                  />
                ))}
              </AnimatePresence>
              {sourceCount > compactReports.length && (
                <div role="listitem" className="orbit-source-overflow">
                  +{sourceCount - compactReports.length} מקורות
                </div>
              )}
            </div>

            <div
              className="orbit-field__strength"
              role="img"
              aria-label={`עוצמת הסיגנל: ${state.label}`}
            >
              <span>{state.label}</span>
              <div aria-hidden>
                {[1, 2, 3, 4].map((level) => (
                  <i key={level} className={level <= state.strength ? "is-on" : ""} />
                ))}
              </div>
              <small>עוצמת הסיגנל</small>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="sr-only" aria-live="polite">
        {arrival ? `${arrival.sourceDisplayName} הצטרף לסיפור` : ""}
      </div>
    </section>
  );
}
