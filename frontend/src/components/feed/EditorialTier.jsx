import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import SourceMeta from "@/components/feed/SourceMeta";
import DeskVoice from "@/components/feed/DeskVoice";
import FeedbackControls from "@/components/feed/FeedbackControls";
import SectionHeading from "@/components/feed/SectionHeading";
import { buildKicker } from "@/components/feed/storyLabels";

// "במוקד" — the high_feed tier. Asymmetric editorial blocks: the first
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
    <motion.article
      variants={variants}
      className={cn(
        "group min-w-0 transition-transform duration-200 hover:-translate-y-px",
        major && "md:col-span-2"
      )}
    >
      {kicker && (
        <p className="text-[11px] font-semibold tracking-wide text-signal-high">{kicker}</p>
      )}

      <h3
        className={cn(
          "mt-1.5 font-display font-bold text-foreground text-balance tracking-[-0.005em]",
          major
            ? "text-[1.2rem] leading-[1.32] md:text-[1.75rem] md:leading-[1.24]"
            : "text-[0.95rem] leading-[1.36] md:text-[1.2rem]"
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

      {item.subtitle && (
        <p
          className={cn(
            "mt-2 text-text-secondary leading-relaxed",
            major ? "text-sm md:text-[0.95rem] max-w-3xl" : "text-[13px]"
          )}
        >
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
    <section aria-label="במוקד">
      <motion.div variants={headingVariants}>
        <SectionHeading className="mb-6">במוקד</SectionHeading>
      </motion.div>
      <div className="grid gap-x-10 gap-y-9 md:grid-cols-2">
        {items.map((item, i) => (
          <EditorialBlock key={item.id} item={item} major={i === 0} variants={variants} />
        ))}
      </div>
    </section>
  );
}
