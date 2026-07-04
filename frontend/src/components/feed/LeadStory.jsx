import React from "react";
import { ArrowUpLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import SourceMeta from "@/components/feed/SourceMeta";
import DeskVoice from "@/components/feed/DeskVoice";
import FeedbackControls from "@/components/feed/FeedbackControls";
import { buildKicker } from "@/components/feed/storyLabels";

// The lead story: the edition's front-page moment. No card, no border —
// a display-serif headline sitting directly on the canvas, with a soft
// signal-tinted aura and a faint court-arc behind it.
export default function LeadStory({ item }) {
  const isPush = item.score?.decision === "push";
  const isCluster = item.type === "cluster";
  const title = isCluster ? item.clusterTitle : item.translatedTitle || item.title;
  const url = isCluster ? null : item.url;
  const kicker = buildKicker(item);
  const publishedAt = item.publishedAt || item.firstSeenAt;
  const sourceLine = isCluster
    ? (item.sourceDisplayNames || []).join(" · ")
    : item.sourceDisplayName;

  const tone = isPush
    ? {
        aura: "radial-gradient(ellipse 70% 60% at 30% 0%, hsl(var(--signal-push) / 0.11), transparent 65%)",
        kicker: "text-signal-push",
        button:
          "border-signal-push/40 text-signal-push hover:bg-signal-push/10 hover:border-signal-push/60",
        underline: "hover:decoration-signal-push/50",
      }
    : {
        aura: "radial-gradient(ellipse 70% 60% at 30% 0%, hsl(var(--signal-high) / 0.08), transparent 65%)",
        kicker: "text-signal-high",
        button:
          "border-signal-high/40 text-signal-high hover:bg-signal-high/10 hover:border-signal-high/60",
        underline: "hover:decoration-signal-high/50",
      };

  const headline = (
    <h2
      className={cn(
        "font-display font-extrabold text-foreground text-balance",
        "text-[2rem] leading-[1.12] md:text-5xl md:leading-[1.08]"
      )}
    >
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className={cn(
            "transition-colors underline decoration-transparent decoration-2 underline-offset-8",
            tone.underline
          )}
        >
          {title}
        </a>
      ) : (
        title
      )}
    </h2>
  );

  return (
    <section aria-label="הסיפור המוביל" className="relative pt-2 pb-4 md:pt-4 md:pb-6">
      {/* Signal aura — the light the story emits. Push breathes slowly. */}
      <div
        aria-hidden
        className={cn(
          "absolute -inset-x-8 -top-12 bottom-0 pointer-events-none blur-2xl",
          isPush && "animate-breathe"
        )}
        style={{ background: tone.aura }}
      />
      {/* Court-line arc, whisper opacity — identity, not decoration. */}
      <svg
        aria-hidden
        viewBox="0 0 300 300"
        className="absolute -top-10 start-0 w-72 h-72 pointer-events-none text-foreground opacity-[0.04]"
        fill="none"
      >
        <circle cx="0" cy="0" r="240" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="0" cy="0" r="160" stroke="currentColor" strokeWidth="1" />
      </svg>

      <div className="relative">
        <div className={cn("flex items-center gap-2 text-xs font-semibold tracking-wide", tone.kicker)}>
          {isPush && (
            <span className="relative flex h-2 w-2" aria-hidden>
              <span className="absolute inline-flex h-full w-full rounded-full bg-signal-push opacity-60 animate-ping" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-signal-push" />
            </span>
          )}
          <span>
            {isPush && "מבזק"}
            {isPush && kicker && " · "}
            {kicker}
          </span>
        </div>

        <div className="mt-2.5">{headline}</div>

        {item.subtitle && (
          <p className="mt-3 text-base md:text-lg text-text-secondary leading-relaxed max-w-3xl line-clamp-3">
            {item.subtitle}
          </p>
        )}

        <DeskVoice reasoning={item.score?.reasoning} variant="full" className="mt-4" />

        <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-3">
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-4 py-2 text-sm font-medium transition-colors",
                tone.button
              )}
            >
              קרא את הכתבה
              <ArrowUpLeft size={14} />
            </a>
          )}
          <SourceMeta source={sourceLine} publishedAt={publishedAt} />
          <FeedbackControls articleId={item.id} variant="text" />
        </div>
      </div>
    </section>
  );
}
