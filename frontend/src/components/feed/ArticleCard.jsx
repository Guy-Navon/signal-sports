import React from "react";
import { ArrowUpLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { getDecisionConfig } from "@/components/feed/decisionConfig";
import DecisionBadge from "@/components/feed/DecisionBadge";
import SignalRail from "@/components/feed/SignalRail";
import SourceMeta from "@/components/feed/SourceMeta";
import EntityChips from "@/components/feed/EntityChips";
import RelevanceReason from "@/components/feed/RelevanceReason";
import FeedbackControls from "@/components/feed/FeedbackControls";

// Title sizing follows relevance: important stories read bigger.
const TITLE_SIZE = {
  push: "text-xl md:text-2xl",
  high_feed: "text-lg md:text-xl",
  feed: "text-base md:text-lg",
  low_feed: "text-sm md:text-base",
  hidden: "text-sm",
};

export default function ArticleCard({ item, hero = false, index = 0 }) {
  const decision = item.score?.decision || "feed";
  const config = getDecisionConfig(decision);
  const isCluster = item.type === "cluster";

  // Hebrew-first: prefer translated title, fall back to raw title.
  const displayTitle = isCluster ? item.clusterTitle : item.translatedTitle || item.title;
  const source = isCluster ? item.sourceDisplayNames?.[0] : item.sourceDisplayName;
  const publishedAt = item.publishedAt || item.firstSeenAt;
  const url = isCluster ? null : item.url;
  const reasoning = item.score?.reasoning || [];

  const extraSources =
    isCluster && item.sourceDisplayNames?.length > 1 ? item.sourceDisplayNames.slice(1) : [];

  // Chips: entities first, fall back to tags. Push/high get chips; quieter levels stay clean.
  const chipSource = (item.entities?.length ? item.entities : item.tags) || [];
  const showChips = decision === "push" || decision === "high_feed" || hero;

  const titleSize = hero ? "text-2xl md:text-3xl" : TITLE_SIZE[decision] || TITLE_SIZE.feed;

  return (
    <article
      style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }}
      className={cn(
        "group relative animate-fade-up",
        "rounded-2xl border border-border bg-surface-1 elevation-1",
        "ps-5 pe-4 py-4 transition-all duration-200",
        "hover:-translate-y-px hover:border-border/80 hover:bg-surface-2/60",
        decision === "push" && "glow-push border-signal-push/20",
        decision === "low_feed" && "opacity-80 hover:opacity-100"
      )}
    >
      <SignalRail decision={decision} />

      {/* Meta row: decision badge (start) · source + time (end) */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <DecisionBadge decision={decision} size="xs" />
        <SourceMeta source={source} publishedAt={publishedAt} extraSourceCount={extraSources.length} />
      </div>

      {/* Headline — editorial serif for the hero moment, crisp sans elsewhere
          (the high-contrast serif reads thin/grey below hero size) */}
      <h2
        className={cn(
          "font-bold leading-tight tracking-tight",
          hero ? "font-display" : "font-body",
          titleSize,
          config.title
        )}
      >
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer" className="hover:text-signal-high transition-colors">
            {displayTitle}
          </a>
        ) : (
          displayTitle
        )}
      </h2>

      {/* Subtitle */}
      {item.subtitle && (
        <p className="text-sm text-text-secondary mt-1.5 line-clamp-2 leading-relaxed">
          {item.subtitle}
        </p>
      )}

      {/* Cluster "also covered in" */}
      {extraSources.length > 0 && (
        <div className="flex items-center flex-wrap gap-1.5 mt-2 text-xs text-text-dim">
          <span>גם ב:</span>
          {extraSources.slice(0, 3).map((s) => (
            <span key={s} className="text-text-secondary">
              {s}
            </span>
          ))}
        </div>
      )}

      {/* Relevance reason — the product's core "why" line */}
      <RelevanceReason reasoning={reasoning} className="mt-3" />

      {/* Footer: entity chips (start) · open + feedback (end) */}
      <div className="flex items-end justify-between gap-3 mt-3 pt-3 border-t border-border/60">
        {showChips ? (
          <EntityChips items={chipSource} max={hero ? 4 : 3} className="min-w-0" />
        ) : (
          <span />
        )}
        <div className="flex items-center gap-1 flex-shrink-0">
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-text-secondary hover:text-signal-high transition-colors px-2 py-1.5"
            >
              <ArrowUpLeft size={13} />
              פתח כתבה
            </a>
          )}
          <FeedbackControls articleId={item.id} />
        </div>
      </div>
    </article>
  );
}
