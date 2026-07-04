import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowUpLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { getDecisionConfig } from "@/components/feed/decisionConfig";
import SourceMeta from "@/components/feed/SourceMeta";
import DeskVoice from "@/components/feed/DeskVoice";
import FeedbackControls from "@/components/feed/FeedbackControls";
import { buildKicker } from "@/components/feed/storyLabels";

// Signal-strength instrument: four ascending bars, filled to the story's
// strength (decisionConfig). A quiet sports-tech accent, not a widget.
function SignalStrength({ decision, tone }) {
  const strength = getDecisionConfig(decision).strength;
  return (
    <div className="flex flex-col items-center gap-1.5" aria-hidden>
      <div className="flex items-end gap-[3px]">
        {[1, 2, 3, 4].map((i) => (
          <span
            key={i}
            className={cn(
              "w-[4px] rounded-full transition-colors",
              i <= strength ? tone.bar : "bg-surface-3"
            )}
            style={{ height: `${6 + i * 5}px` }}
          />
        ))}
      </div>
      <span className="text-[9px] tracking-[0.18em] text-text-dim font-mono">SIGNAL</span>
    </div>
  );
}

// Half-court geometry that draws itself in on mount — identity, not clip-art.
// Anchored to the inline-end of the hero band at whisper opacity.
function CourtLines({ reduce }) {
  const draw = reduce
    ? {}
    : {
        initial: { pathLength: 0, opacity: 0 },
        animate: { pathLength: 1, opacity: 1 },
        transition: { duration: 1.6, ease: "easeOut", delay: 0.3 },
      };
  return (
    <svg
      aria-hidden
      viewBox="0 0 420 420"
      fill="none"
      className="absolute top-1/2 -translate-y-1/2 end-[-60px] h-[130%] w-auto pointer-events-none text-foreground opacity-[0.055] rtl:-scale-x-100"
    >
      {/* three-point arc */}
      <motion.path d="M 420 30 A 195 195 0 0 0 420 390" stroke="currentColor" strokeWidth="1.5" {...draw} />
      {/* key / paint */}
      <motion.path d="M 420 145 H 300 V 275 H 420" stroke="currentColor" strokeWidth="1.2" {...draw} />
      {/* free-throw circle */}
      <motion.circle cx="300" cy="210" r="46" stroke="currentColor" strokeWidth="1.2" {...draw} />
      {/* rim + backboard hint */}
      <motion.path d="M 420 190 V 230 M 404 210 a 8 8 0 1 0 -0.1 0" stroke="currentColor" strokeWidth="1.2" {...draw} />
    </svg>
  );
}

// The lead story: the edition's front-page moment, composed as a full-width
// hero band — layered signal mesh, court geometry, serif headline, the desk's
// voice, and a signal-strength instrument. No card, no border.
export default function LeadStory({ item }) {
  const reduce = useReducedMotion();
  const decision = item.score?.decision || "high_feed";
  const isPush = decision === "push";
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
        mesh: `radial-gradient(ellipse 55% 90% at 18% 0%, hsl(var(--signal-push) / 0.13), transparent 62%),
               radial-gradient(ellipse 40% 70% at 85% 100%, hsl(var(--signal-ai) / 0.05), transparent 60%)`,
        kicker: "text-signal-push",
        bar: "bg-signal-push",
        button:
          "border-signal-push/40 text-signal-push hover:bg-signal-push/10 hover:border-signal-push/60 hover:shadow-[0_0_18px_hsl(var(--signal-push)/0.15)]",
        underline: "hover:decoration-signal-push/40",
        rule: "from-signal-push/50",
      }
    : {
        mesh: `radial-gradient(ellipse 55% 90% at 18% 0%, hsl(var(--signal-high) / 0.09), transparent 62%),
               radial-gradient(ellipse 40% 70% at 85% 100%, hsl(var(--signal-ai) / 0.04), transparent 60%)`,
        kicker: "text-signal-high",
        bar: "bg-signal-high",
        button:
          "border-signal-high/40 text-signal-high hover:bg-signal-high/10 hover:border-signal-high/60 hover:shadow-[0_0_18px_hsl(var(--signal-high)/0.15)]",
        underline: "hover:decoration-signal-high/40",
        rule: "from-signal-high/50",
      };

  return (
    <section
      aria-label="הסיפור המרכזי"
      className="relative -mx-4 px-4 pt-7 pb-8 md:pt-9 md:pb-10 overflow-hidden"
    >
      {/* Atmosphere: layered signal mesh (breathes for push) + court geometry */}
      <div
        aria-hidden
        className={cn("absolute inset-0 pointer-events-none", isPush && "animate-breathe")}
        style={{ background: tone.mesh }}
      />
      <CourtLines reduce={reduce} />
      {/* Hairline that fades out toward the inline-end — grounds the band */}
      <div
        aria-hidden
        className={cn("absolute bottom-0 inset-x-4 h-px bg-gradient-to-l to-transparent", tone.rule)}
      />

      <div className="relative flex items-start justify-between gap-6">
        <div className="min-w-0 max-w-4xl">
          <div className={cn("flex items-center gap-2 text-xs font-semibold tracking-wide", tone.kicker)}>
            {isPush && (
              <span className="relative flex h-2 w-2" aria-hidden>
                <span className="absolute inline-flex h-full w-full rounded-full bg-signal-push opacity-60 animate-ping" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-signal-push" />
              </span>
            )}
            <span>
              הסיפור המרכזי
              {kicker && ` · ${kicker}`}
            </span>
          </div>

          <h2
            className={cn(
              "mt-3 font-display font-bold text-foreground text-balance",
              "text-[1.4rem] leading-[1.3] md:text-[2.6rem] md:leading-[1.16] xl:text-[2.9rem]",
              "tracking-[-0.01em]"
            )}
          >
            {url ? (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className={cn(
                  "transition-colors underline decoration-transparent decoration-2 underline-offset-[10px]",
                  tone.underline
                )}
              >
                {title}
              </a>
            ) : (
              title
            )}
          </h2>

          {item.subtitle && (
            <p className="mt-3.5 text-[0.95rem] md:text-[1.05rem] text-text-secondary leading-relaxed max-w-2xl">
              {item.subtitle}
            </p>
          )}

          <DeskVoice reasoning={item.score?.reasoning} variant="full" className="mt-4" />

          <div className="mt-2.5">
            <SourceMeta source={sourceLine} publishedAt={publishedAt} />
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-3">
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-4 py-2 text-sm font-medium transition-all",
                  tone.button
                )}
              >
                קרא את הכתבה
                <ArrowUpLeft size={14} />
              </a>
            )}
            <FeedbackControls articleId={item.id} variant="text" />
          </div>
        </div>

        <div className="hidden md:flex flex-col items-center pt-1 flex-shrink-0">
          <SignalStrength decision={decision} tone={tone} />
        </div>
      </div>
    </section>
  );
}
