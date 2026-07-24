import React, { useState } from "react";
import { ArrowUpLeft, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import ClusterSources from "./ClusterSources";
import { getDecisionConfig } from "@/components/feed/decisionConfig";
import SourceMeta from "@/components/feed/SourceMeta";
import DeskVoice from "@/components/feed/DeskVoice";
import FeedbackControls from "@/components/feed/FeedbackControls";
import { buildKicker } from "@/components/feed/storyLabels";

// "עוד מהפיד" — a regular story as a typographic row, not a card. Headline + one
// quiet meta line; subtitle and the desk's reasoning expand inline on demand.
// In the filtered view (showLevelDot) the row also carries its level as a dot
// and scales its headline with relevance.
const FILTERED_TITLE_SIZE = {
  push: "text-lg md:text-xl font-display font-bold",
  high_feed: "text-[1.05rem] md:text-lg font-semibold",
  feed: "text-[1.05rem] font-semibold",
  low_feed: "text-sm font-medium text-text-secondary",
};

export default function StreamRow({ item, showLevelDot = false }) {
  const [open, setOpen] = useState(false);
  const decision = item.score?.decision || "feed";
  const config = getDecisionConfig(decision);
  const isCluster = item.type === "cluster";
  const title = isCluster ? item.clusterTitle : item.translatedTitle || item.title;
  const url = isCluster ? null : item.url;
  const kicker = buildKicker(item);
  const sourceLine = isCluster
    ? (item.sourceDisplayNames || [])[0]
    : item.sourceDisplayName;
  const extraSources = isCluster ? Math.max((item.sourceDisplayNames || []).length - 1, 0) : 0;
  // Subtitle is always visible now; the expander reveals the desk's reasoning.
  const hasDetail = Boolean(item.score?.reasoning?.length);

  const titleClass = showLevelDot
    ? FILTERED_TITLE_SIZE[decision] || FILTERED_TITLE_SIZE.feed
    : "text-[1.05rem] font-semibold";

  return (
    <article
      className={cn(
        "group relative px-2 py-4 transition-colors sm:px-3",
        "hover:bg-surface-1/65"
      )}
    >
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-start gap-2 sm:gap-3">
        <div className="min-w-0">
          <h3 className={cn("leading-[1.4] text-foreground", titleClass)}>
            {url ? (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="transition-colors underline decoration-transparent underline-offset-4 hover:decoration-text-dim/60"
              >
                {title}
              </a>
            ) : (
              title
            )}
          </h3>
          {item.subtitle && (
            <p className="mt-1 text-[13px] text-text-secondary leading-relaxed line-clamp-2 max-w-3xl">
              {item.subtitle}
            </p>
          )}
          {isCluster && <ClusterSources item={item} />}
          <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            {showLevelDot && (
              <span
                className={cn("inline-block w-1.5 h-1.5 rounded-full flex-shrink-0", config.dot)}
                title={config.label}
                aria-label={config.label}
              />
            )}
            {kicker && <span className="text-text-dim font-medium">{kicker}</span>}
            {kicker && <span className="text-text-dim/60" aria-hidden>·</span>}
            <SourceMeta
              source={sourceLine}
              publishedAt={item.publishedAt || item.firstSeenAt}
              extraSourceCount={extraSources}
            />
          </div>
        </div>

        <div
          className={cn(
            "flex flex-shrink-0 items-center gap-0.5 pt-0.5 transition-opacity",
            "opacity-75 md:opacity-0 md:group-hover:opacity-100 md:focus-within:opacity-100"
          )}
        >
          {hasDetail && (
            <button
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              aria-label="פרטים נוספים"
              title="פרטים נוספים"
              className="p-1.5 rounded-md text-text-dim hover:text-signal-ai hover:bg-signal-ai/10 transition-colors"
            >
              <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />
            </button>
          )}
          <FeedbackControls articleId={item.id} />
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="פתח כתבה"
              title="פתח כתבה"
              className="p-1.5 rounded-md text-text-dim hover:text-signal-high hover:bg-signal-high/10 transition-colors"
            >
              <ArrowUpLeft size={14} />
            </a>
          )}
        </div>
      </div>

      {open && (
        <div className="mt-2 mb-1 pe-1">
          <DeskVoice reasoning={item.score?.reasoning} variant="line" />
        </div>
      )}
    </article>
  );
}
