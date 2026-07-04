import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import SourceMeta from "@/components/feed/SourceMeta";
import DeskVoice from "@/components/feed/DeskVoice";
import FeedbackControls from "@/components/feed/FeedbackControls";
import SectionHeading from "@/components/feed/SectionHeading";
import { buildKicker } from "@/components/feed/storyLabels";

// "חשובים עכשיו" — the high_feed tier. Asymmetric editorial blocks: the first
// story spans the full width at a larger scale, the rest sit in a two-column
// grid. Typography and whitespace do the hierarchy; no boxes.
function EditorialBlock({ item, major = false, variants = undefined }) {
  const isCluster = item.type === "cluster";
  const title = isCluster ? item.clusterTitle : item.translatedTitle || item.title;
  const url = isCluster ? null : item.url;
  const kicker = buildKicker(item);
  const sourceLine = isCluster
    ? (item.sourceDisplayNames || []).join(" · ")
    : item.sourceDisplayName;

  return (
    <motion.article variants={variants} className={cn("group min-w-0", major && "md:col-span-2")}>
      {kicker && (
        <p className="text-xs font-semibold tracking-wide text-signal-high">{kicker}</p>
      )}

      <h3
        className={cn(
          "mt-1.5 font-display font-bold text-foreground text-balance",
          major
            ? "text-[1.6rem] leading-snug md:text-3xl md:leading-[1.2]"
            : "text-xl leading-snug md:text-[1.35rem]"
        )}
      >
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="transition-colors underline decoration-transparent decoration-2 underline-offset-4 hover:decoration-signal-high/50"
          >
            {title}
          </a>
        ) : (
          title
        )}
      </h3>

      {major && item.subtitle && (
        <p className="mt-2 text-sm md:text-base text-text-secondary leading-relaxed max-w-3xl line-clamp-2">
          {item.subtitle}
        </p>
      )}

      <DeskVoice
        reasoning={item.score?.reasoning}
        variant={major ? "full" : "line"}
        className="mt-2.5"
      />

      <div className="mt-2.5 flex items-center justify-between gap-3">
        <SourceMeta source={sourceLine} publishedAt={item.publishedAt || item.firstSeenAt} />
        <FeedbackControls
          articleId={item.id}
          className="opacity-60 md:opacity-0 md:group-hover:opacity-100 md:focus-within:opacity-100 transition-opacity"
        />
      </div>
    </motion.article>
  );
}

export default function EditorialTier({ items, variants = undefined, headingVariants = undefined }) {
  if (!items.length) return null;
  return (
    <section aria-label="חשובים עכשיו">
      <motion.div variants={headingVariants}>
        <SectionHeading className="mb-6">חשובים עכשיו</SectionHeading>
      </motion.div>
      <div className="grid gap-x-10 gap-y-9 md:grid-cols-2">
        {items.map((item, i) => (
          <EditorialBlock key={item.id} item={item} major={i === 0} variants={variants} />
        ))}
      </div>
    </section>
  );
}
