import React from "react";
import { Clock } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { he } from "date-fns/locale";

function formatTime(dateStr) {
  try {
    return formatDistanceToNow(new Date(dateStr), { addSuffix: true, locale: he });
  } catch {
    return dateStr;
  }
}

// Quiet metadata line: source · additional-sources · relative time.
export default function SourceMeta({ source, publishedAt, extraSourceCount = 0 }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-text-secondary">
      <span className="max-w-full truncate font-semibold text-foreground/75">{source}</span>
      {extraSourceCount > 0 && (
        <span className="text-text-dim flex-shrink-0">+{extraSourceCount} מקורות</span>
      )}
      <span className="text-text-dim flex-shrink-0">·</span>
      <span className="flex items-center gap-1 text-text-dim flex-shrink-0">
        <Clock size={10} />
        {formatTime(publishedAt)}
      </span>
    </div>
  );
}
