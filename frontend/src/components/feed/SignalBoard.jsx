import React, { useMemo } from "react";
import { Sparkles } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { he } from "date-fns/locale";
import SignalSpectrum from "@/components/feed/SignalSpectrum";
import TopicFilters from "@/components/feed/TopicFilters";
import MonoValue from "@/components/shared/MonoValue";

function BoardLabel({ children }) {
  return (
    <p className="text-[10.5px] font-semibold tracking-[0.14em] text-text-dim mb-3">{children}</p>
  );
}

// "לוח הסיגנל" — the desk's side board on wide screens: the spectrum, topic
// filters, and a few quiet desk facts. Derived entirely from data already on
// the page; deliberately prose-and-lines, not stat cards.
export default function SignalBoard({
  counts,
  activeFilters,
  onToggle,
  onReset,
  items,
  scanned = 0,
}) {
  const facts = useMemo(() => {
    const sources = new Set();
    let latest = null;
    for (const item of items) {
      if (item.type === "cluster") {
        (item.sourceDisplayNames || []).forEach((s) => sources.add(s));
      } else if (item.sourceDisplayName) {
        sources.add(item.sourceDisplayName);
      }
      const t = new Date(item.publishedAt || item.firstSeenAt || 0).getTime();
      if (t && (!latest || t > latest)) latest = t;
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
    <div className="border-s border-border/50 ps-7">
      <BoardLabel>לוח הסיגנל</BoardLabel>
      <SignalSpectrum
        counts={counts}
        activeFilters={activeFilters}
        onToggle={onToggle}
        vertical
      />

      <div className="my-6 h-px bg-border/50" aria-hidden />

      <BoardLabel>סינון מהיר</BoardLabel>
      <TopicFilters
        activeFilters={activeFilters}
        onToggle={onToggle}
        onReset={onReset}
        vertical
      />

      <div className="my-6 h-px bg-border/50" aria-hidden />

      <div className="space-y-2 text-xs text-text-dim leading-relaxed">
        <p className="flex items-center gap-1.5">
          <Sparkles size={11} className="text-signal-ai flex-shrink-0" />
          <span>
            המערכת סרקה <MonoValue className="text-text-secondary">{scanned}</MonoValue> כתבות
            {facts.sourceCount > 0 && (
              <>
                {" "}
                מ־<MonoValue className="text-text-secondary">{facts.sourceCount}</MonoValue> מקורות
              </>
            )}
          </span>
        </p>
        {facts.latestAgo && <p>עדכון אחרון: {facts.latestAgo}</p>}
      </div>
    </div>
  );
}
