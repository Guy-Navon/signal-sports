import { useState } from "react";
import { cn } from "@/lib/utils";
import { clusterAlternates, clusterSourceCount, shouldShowSources } from "./clusterModel";
import { formatDistanceToNow } from "date-fns";
import { he } from "date-fns/locale";

function relTime(dateStr) {
  try {
    return formatDistanceToNow(new Date(dateStr), { addSuffix: true, locale: he });
  } catch {
    return dateStr;
  }
}

/**
 * "עוד מקורות" — the collapsed alternate-coverage disclosure on a story-cluster card (#104).
 *
 * Renders VISIBLE members only. The backend never sends suppressed members in the consumer
 * payload (docs/CLUSTERING.md §9), so a hidden article cannot leak here even by accident —
 * clustering must not resurrect content a user's preferences hid.
 *
 * Collapsed by default: the feed stays one card per story, not a nested article list.
 */
export default function ClusterSources({ item }) {
  const [open, setOpen] = useState(false);

  // All rules live in clusterModel.js (repo convention: components render, models decide).
  const alternates = clusterAlternates(item);
  const sourceCount = clusterSourceCount(item);

  if (!shouldShowSources(item)) return null;

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        data-testid="cluster-sources-toggle"
        className={cn(
          "inline-flex items-center gap-1.5 text-xs font-medium",
          "text-muted-foreground hover:text-foreground transition-colors"
        )}
      >
        <span
          data-testid="cluster-source-count"
          className="rounded-full bg-surface-2 px-2 py-0.5 tabular-nums"
        >
          {sourceCount} מקורות
        </span>
        <span>{open ? "הסתר" : "עוד מקורות"}</span>
      </button>

      {open && (
        <ul data-testid="cluster-sources-list" className="mt-2 space-y-1.5 border-r-2 border-surface-2 pr-3">
          {alternates.map(m => (
            <li key={m.articleId} className="text-xs leading-snug">
              <a
                href={m.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-foreground/80 hover:text-foreground hover:underline"
              >
                {m.title}
              </a>
              <div className="mt-0.5 flex items-center gap-2 text-[0.7rem] text-muted-foreground">
                <span>{m.sourceDisplayName}</span>
                <span aria-hidden>·</span>
                <time dateTime={m.publishedAt}>{relTime(m.publishedAt)}</time>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
