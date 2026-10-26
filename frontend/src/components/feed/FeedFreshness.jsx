import React, { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Clock } from "lucide-react";
import { getMeFeedFreshness } from "@/api/client";
import { feedFreshnessView } from "@/components/feed/feedFreshnessModel";

const REFRESH_MS = 60_000;

// One quiet line over the feed: "עודכן לפני 4 דק׳", or a plain warning when
// automatic ingestion has stopped (#249). Backend mode only; on a failed
// request it renders nothing (the feed shows its own connection error).
export default function FeedFreshness({ enabled }) {
  const { data } = useQuery({
    queryKey: ["me", "feed-freshness"],
    queryFn: getMeFeedFreshness,
    enabled,
    refetchInterval: REFRESH_MS,
  });
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return undefined;
    const id = setInterval(() => setNow(Date.now()), REFRESH_MS);
    return () => clearInterval(id);
  }, [enabled]);

  const view = enabled ? feedFreshnessView(data, now) : null;
  if (!view) return null;

  return (
    <p
      role="status"
      className={
        view.warning
          ? "mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-signal-hidden"
          : "mb-3 flex items-center gap-1.5 text-xs text-text-dim"
      }
    >
      {view.warning ? (
        <AlertTriangle size={14} aria-hidden className="flex-shrink-0" />
      ) : (
        <Clock size={12} aria-hidden className="flex-shrink-0" />
      )}
      {view.warning && <span className="font-medium">{view.warning}</span>}
      <span className={view.warning ? "text-text-secondary text-xs" : undefined}>
        {view.label}
      </span>
    </p>
  );
}
