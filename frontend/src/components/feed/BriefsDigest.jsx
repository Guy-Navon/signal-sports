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
    <div className="group grid min-w-0 gap-1 border-b border-foreground/10 py-2.5 last:border-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-3">
      <p className="min-w-0 text-[13px] leading-relaxed text-text-secondary sm:truncate">
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer" className="hover:text-foreground transition-colors">
            {title}
          </a>
        ) : (
          title
        )}
      </p>
      <div className="flex min-w-0 items-center gap-1.5 sm:flex-shrink-0">
        <span className="truncate text-[11px] text-text-dim">
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
          "ledger-panel px-4 py-2 sm:px-5",
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
