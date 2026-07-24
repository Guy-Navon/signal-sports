import React from "react";
import { ArrowUpLeft, Radio, Layers3 } from "lucide-react";
import { cn } from "@/lib/utils";
import { getDecisionConfig } from "@/components/feed/decisionConfig";
import SourceMeta from "@/components/feed/SourceMeta";
import ClusterSources from "@/components/feed/ClusterSources";
import DeskVoice from "@/components/feed/DeskVoice";
import FeedbackControls from "@/components/feed/FeedbackControls";
import { buildKicker } from "@/components/feed/storyLabels";

function SignalStrength({ decision, barClass }) {
  const strength = getDecisionConfig(decision).strength;
  return (
    <div className="flex items-end gap-1" aria-label={`עוצמת סיגנל ${strength} מתוך 4`}>
      {[1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className={cn("w-2", i <= strength ? barClass : "bg-background/20")}
          style={{ height: `${10 + i * 7}px` }}
        />
      ))}
    </div>
  );
}

// The lead is a real front page: headline and action on paper, live context
// in an ink-black desk column. No imagery is required for the hierarchy to
// survive missing or inconsistent article media.
export default function LeadStory({ item }) {
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
  const sourceCount = isCluster ? item.sourceCount || item.sourceDisplayNames?.length || 0 : 1;

  return (
    <section
      aria-label="הסיפור המרכזי"
      className="editorial-rule-heavy grid min-w-0 border-b border-foreground bg-surface-1/75 lg:grid-cols-[minmax(0,1fr)_250px]"
    >
      <div className="min-w-0 p-5 sm:p-7 lg:p-9">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 px-2 py-1 font-mono text-[10px] font-bold tracking-[0.12em]",
              isPush
                ? "bg-signal-push text-white"
                : "bg-signal-high text-white"
            )}
          >
            <Radio size={11} className={isPush ? "animate-pulse" : ""} />
            {isPush ? "TOP SIGNAL / דחוף" : "TOP STORY / במוקד"}
          </span>
          {kicker && <span className="eyebrow">{kicker}</span>}
        </div>

        <h2 className="mt-4 max-w-5xl text-balance font-display text-[2rem] font-bold leading-[1.04] tracking-[-0.025em] text-foreground sm:text-[3rem] lg:text-[3.65rem]">
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="decoration-2 underline-offset-[10px] transition-colors hover:text-signal-push hover:underline"
            >
              {title}
            </a>
          ) : (
            title
          )}
        </h2>

        {item.subtitle && (
          <p className="mt-4 max-w-3xl text-[0.98rem] leading-relaxed text-text-secondary sm:text-[1.08rem]">
            {item.subtitle}
          </p>
        )}

        <DeskVoice reasoning={item.score?.reasoning} variant="full" className="mt-5 max-w-3xl" />

        <div className="mt-4">
          <SourceMeta source={sourceLine} publishedAt={publishedAt} />
        </div>

        {isCluster && <ClusterSources item={item} />}

        <div className="mt-6 flex flex-wrap items-center gap-3">
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 border border-foreground bg-foreground px-4 py-2 text-sm font-semibold text-background transition-colors hover:bg-signal-push hover:text-white"
            >
              קראו את הכתבה
              <ArrowUpLeft size={15} />
            </a>
          )}
          <FeedbackControls articleId={item.id} variant="text" />
        </div>
      </div>

      <aside className="flex min-w-0 flex-col justify-between gap-7 bg-foreground p-5 text-background sm:p-6 lg:p-7">
        <div>
          <p className="font-mono text-[9px] font-bold tracking-[0.2em] text-background/45">
            SIGNAL STRENGTH
          </p>
          <div className="mt-3 flex items-end justify-between gap-4">
            <SignalStrength
              decision={decision}
              barClass={isPush ? "bg-signal-push" : "bg-signal-high"}
            />
            <span className="font-display text-4xl font-bold leading-none">
              {getDecisionConfig(decision).strength}
              <span className="text-base text-background/40">/4</span>
            </span>
          </div>
        </div>

        <div className="border-t border-background/20 pt-4">
          <p className="font-mono text-[9px] font-bold tracking-[0.2em] text-background/45">
            COVERAGE
          </p>
          <div className="mt-2 flex items-center gap-2">
            <Layers3 size={16} className="text-signal-high" />
            <p className="text-sm font-medium">
              {isCluster ? `${sourceCount} דיווחים בסיפור מתפתח` : "דיווח מקור יחיד"}
            </p>
          </div>
        </div>

        <p className="border-t border-background/20 pt-4 text-xs leading-relaxed text-background/58">
          סדר המהדורה נקבע לפי ההעדפות והכיול שלך, לא לפי סדר הפרסום.
        </p>
      </aside>
    </section>
  );
}
