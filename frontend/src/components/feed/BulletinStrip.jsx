import React from "react";
import { ArrowUpLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import SourceMeta from "@/components/feed/SourceMeta";
import DeskVoice from "@/components/feed/DeskVoice";
import FeedbackControls from "@/components/feed/FeedbackControls";
import { buildKicker } from "@/components/feed/storyLabels";

// מבזק — a push story that isn't the lead. Composed bulletin row with a gold
// bleed from the inline-start edge. Rare by design; reads as an interruption
// without shouting.
export default function BulletinStrip({ item }) {
  const isCluster = item.type === "cluster";
  const title = isCluster ? item.clusterTitle : item.translatedTitle || item.title;
  const url = isCluster ? null : item.url;
  const kicker = buildKicker(item);
  const sourceLine = isCluster
    ? (item.sourceDisplayNames || []).join(" · ")
    : item.sourceDisplayName;

  return (
    <article
      className={cn(
        "relative py-4 px-5 -mx-1 group rounded-xl",
        // Gold bleed from the inline-start edge (RTL-only app: start = right).
        "bg-gradient-to-l from-signal-push/[0.07] via-signal-push/[0.02] to-transparent",
        "transition-colors hover:from-signal-push/[0.1]"
      )}
    >
      <div className="flex items-center gap-2 text-[11px] font-semibold tracking-wide text-signal-push">
        <span className="relative flex h-1.5 w-1.5" aria-hidden>
          <span className="absolute inline-flex h-full w-full rounded-full bg-signal-push opacity-60 animate-ping" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-signal-push" />
        </span>
        <span>מבזק{kicker ? ` · ${kicker}` : ""}</span>
      </div>

      <h3 className="mt-1.5 font-display font-bold text-foreground text-balance text-base md:text-[1.35rem] leading-snug tracking-[-0.005em]">
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="transition-colors underline decoration-transparent decoration-2 underline-offset-4 hover:decoration-signal-push/40"
          >
            {title}
          </a>
        ) : (
          title
        )}
      </h3>

      {item.subtitle && (
        <p className="mt-1.5 text-sm text-text-secondary leading-relaxed line-clamp-2 max-w-3xl">
          {item.subtitle}
        </p>
      )}

      <DeskVoice reasoning={item.score?.reasoning} variant="line" className="mt-2" />

      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <SourceMeta source={sourceLine} publishedAt={item.publishedAt || item.firstSeenAt} />
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-text-secondary hover:text-signal-push transition-colors"
          >
            <ArrowUpLeft size={13} />
            פתח כתבה
          </a>
        )}
        <FeedbackControls
          articleId={item.id}
          variant="text"
          className="opacity-70 md:opacity-0 md:group-hover:opacity-100 md:focus-within:opacity-100 transition-opacity"
        />
      </div>
    </article>
  );
}
