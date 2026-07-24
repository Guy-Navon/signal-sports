import React, { useMemo } from "react";
import { ScanSearch, Radio } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { he } from "date-fns/locale";
import MonoValue from "@/components/shared/MonoValue";

function storyTitle(item) {
  return item.type === "cluster"
    ? item.clusterTitle
    : item.translatedTitle || item.title;
}

// The desktop desk index is a reading aid, not a second set of controls. It
// shows the top three items in order and explains the size/freshness of the
// reporting pool without turning those facts into generic stat cards.
export default function SignalBoard({ items, scanned = 0 }) {
  const facts = useMemo(() => {
    const sources = new Set();
    let latest = null;
    for (const item of items) {
      if (item.type === "cluster") {
        (item.sourceDisplayNames || []).forEach((source) => sources.add(source));
      } else if (item.sourceDisplayName) {
        sources.add(item.sourceDisplayName);
      }
      const timestamp = new Date(item.publishedAt || item.firstSeenAt || 0).getTime();
      if (timestamp && (!latest || timestamp > latest)) latest = timestamp;
    }
    let latestAgo = null;
    if (latest) {
      try {
        latestAgo = formatDistanceToNow(new Date(latest), { addSuffix: true, locale: he });
      } catch {
        latestAgo = null;
      }
    }
    return { sourceCount: sources.size, latestAgo };
  }, [items]);

  return (
    <div className="border-t-4 border-foreground">
      <div className="flex items-center justify-between border-b border-foreground/20 py-2">
        <p className="eyebrow text-foreground">DESK INDEX / סדר קריאה</p>
        <Radio size={13} className="text-signal-push" />
      </div>

      <ol>
        {items.slice(0, 3).map((item, index) => (
          <li
            key={item.id}
            className="grid grid-cols-[1.6rem_1fr] gap-2 border-b border-foreground/15 py-3"
          >
            <span className="font-mono text-[10px] font-bold text-signal-push">
              {String(index + 1).padStart(2, "0")}
            </span>
            <p className="line-clamp-3 text-xs font-medium leading-relaxed text-foreground">
              {storyTitle(item)}
            </p>
          </li>
        ))}
      </ol>

      <div className="mt-5 bg-foreground p-4 text-background">
        <div className="flex items-center gap-2">
          <ScanSearch size={14} className="text-signal-high" />
          <p className="font-mono text-[9px] font-bold tracking-[0.14em] text-background/50">
            LIVE INTAKE
          </p>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-background/70">
          נסרקו <MonoValue className="font-bold text-background">{scanned}</MonoValue> כתבות
          {facts.sourceCount > 0 && (
            <>
              {" "}מ־<MonoValue className="font-bold text-background">{facts.sourceCount}</MonoValue> מקורות
            </>
          )}
          .
        </p>
        {facts.latestAgo && (
          <p className="mt-1 text-xs text-background/48">הדיווח האחרון {facts.latestAgo}</p>
        )}
      </div>
    </div>
  );
}
