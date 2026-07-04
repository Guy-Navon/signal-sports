import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";
import { he } from "date-fns/locale";
import SectionHeading from "@/components/feed/SectionHeading";
import FeedbackControls from "@/components/feed/FeedbackControls";

function timeAgo(dateStr) {
  try {
    return formatDistanceToNow(new Date(dateStr), { addSuffix: true, locale: he });
  } catch {
    return "";
  }
}

const COLLAPSED_COUNT = 4;

// "קריאה נוספת" — the low_feed digest, intentionally compressed: a quiet inset
// band of one-liners in two columns. Low-priority stories cost almost no
// vertical space — the signal-over-noise thesis rendered as layout.
function BriefRow({ item }) {
  const isCluster = item.type === "cluster";
  const title = isCluster ? item.clusterTitle : item.translatedTitle || item.title;
  const url = isCluster ? null : item.url;
  const source = isCluster
    ? (item.sourceDisplayNames || [])[0]
    : item.sourceDisplayName;

  return (
    <div className="group flex items-center justify-between gap-3 py-1.5 min-w-0">
      <p className="min-w-0 truncate text-[13px] text-text-secondary leading-relaxed">
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer" className="hover:text-foreground transition-colors">
            {title}
          </a>
        ) : (
          title
        )}
      </p>
      <div className="flex items-center gap-1.5 flex-shrink-0">
        <span className="text-[11px] text-text-dim">
          {source} · {timeAgo(item.publishedAt || item.firstSeenAt)}
        </span>
        <FeedbackControls
          articleId={item.id}
          className="opacity-60 md:opacity-0 md:group-hover:opacity-100 md:focus-within:opacity-100 transition-opacity"
        />
      </div>
    </div>
  );
}

export default function BriefsDigest({ items }) {
  const [expanded, setExpanded] = useState(false);
  if (!items.length) return null;

  const visible = expanded ? items : items.slice(0, COLLAPSED_COUNT);
  const hiddenCount = items.length - COLLAPSED_COUNT;

  return (
    <section aria-label="קריאה נוספת">
      <SectionHeading
        count={items.length}
        className="mb-3"
        action={
          hiddenCount > 0 ? (
            <button
              onClick={() => setExpanded((e) => !e)}
              className="text-xs text-signal-high hover:text-signal-high/80 transition-colors flex-shrink-0"
            >
              {expanded ? "צמצם" : `הצג את כל ה־${items.length}`}
            </button>
          ) : null
        }
      >
        קריאה נוספת
      </SectionHeading>
      <div
        className={cn(
          "rounded-2xl bg-surface-1/35 px-5 py-3",
          "md:grid md:grid-cols-2 md:gap-x-10"
        )}
      >
        {visible.map((item) => (
          <BriefRow key={item.id} item={item} />
        ))}
      </div>
    </section>
  );
}
