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

const COLLAPSED_COUNT = 2;

// "בקצרה" — the low_feed digest. Low-priority stories stop costing vertical
// space: a collapsed list of one-liners with an expand toggle. This is the
// signal-over-noise thesis rendered as layout.
function BriefRow({ item }) {
  const isCluster = item.type === "cluster";
  const title = isCluster ? item.clusterTitle : item.translatedTitle || item.title;
  const url = isCluster ? null : item.url;
  const source = isCluster
    ? (item.sourceDisplayNames || [])[0]
    : item.sourceDisplayName;

  return (
    <div className="group flex items-center justify-between gap-3 py-2">
      <p className="min-w-0 truncate text-sm text-text-secondary">
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer" className="hover:text-foreground transition-colors">
            {title}
          </a>
        ) : (
          title
        )}
      </p>
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="text-xs text-text-dim">
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
    <section aria-label="בקצרה">
      <SectionHeading
        count={items.length}
        className="mb-2"
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
        בקצרה
      </SectionHeading>
      <div className={cn("divide-y divide-border/40", !expanded && hiddenCount > 0 && "pb-1")}>
        {visible.map((item) => (
          <BriefRow key={item.id} item={item} />
        ))}
      </div>
    </section>
  );
}
