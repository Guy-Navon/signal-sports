import React from "react";
import { ArrowUpLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import SourceMeta from "@/components/feed/SourceMeta";
import DeskVoice from "@/components/feed/DeskVoice";
import FeedbackControls from "@/components/feed/FeedbackControls";
import { buildKicker } from "@/components/feed/storyLabels";

// מבזק — a push story that isn't the lead. Full-width bulletin strip with a
// gold tint bleeding from the inline-start edge. Rare by design; when it
// appears, it should read as an interruption.
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
        "relative py-5 px-4 -mx-4 group",
        // Gold bleed from the inline-start edge (RTL: start = right → gradient to-left).
        "bg-gradient-to-l from-signal-push/[0.06] via-transparent to-transparent"
      )}
    >
      <div className="flex items-center gap-2 text-xs font-semibold tracking-wide text-signal-push">
        <span className="relative flex h-1.5 w-1.5" aria-hidden>
          <span className="absolute inline-flex h-full w-full rounded-full bg-signal-push opacity-60 animate-ping" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-signal-push" />
        </span>
        <span>מבזק{kicker ? ` · ${kicker}` : ""}</span>
      </div>

      <h3 className="mt-2 font-display font-bold text-foreground text-balance text-xl md:text-[1.65rem] md:leading-snug">
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="transition-colors underline decoration-transparent decoration-2 underline-offset-4 hover:decoration-signal-push/50"
          >
            {title}
          </a>
        ) : (
          title
        )}
      </h3>

      <DeskVoice reasoning={item.score?.reasoning} variant="full" className="mt-2.5" />

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
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
        <FeedbackControls articleId={item.id} variant="text" />
      </div>
    </article>
  );
}
