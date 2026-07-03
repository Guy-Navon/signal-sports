import React, { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import DecisionBadge from "@/components/feed/DecisionBadge";

function ComparisonRow({ item, profiles }) {
  const [expanded, setExpanded] = useState(false);
  const title = item.type === "cluster" ? item.clusterTitle : item.title;
  const profileIds = Object.keys(item.profileScores || {});

  const decisions = profileIds.map((pid) => item.profileScores[pid]?.decision);
  const disagreement = new Set(decisions).size > 1;

  return (
    <div
      className={cn(
        "border rounded-xl overflow-hidden",
        disagreement ? "border-signal-ai/30 bg-signal-ai/5" : "border-border bg-surface-1"
      )}
    >
      <button
        className="w-full text-start p-3 flex items-start justify-between gap-3 hover:bg-surface-2/50 transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="flex-1 min-w-0">
          {disagreement && (
            <span className="text-[10px] text-signal-ai bg-signal-ai/10 border border-signal-ai/25 rounded-full px-1.5 py-0.5 mb-1 inline-block">
              חוסר הסכמה
            </span>
          )}
          <p className="text-sm text-foreground font-medium leading-snug truncate">{title}</p>
          <p className="text-xs text-text-dim mt-0.5">
            {item.sport} · {item.league || "—"} · {item.eventType || "—"}
          </p>
        </div>
        <div className="flex flex-col gap-1 flex-shrink-0 items-end">
          {profileIds.map((pid) => (
            <div key={pid} className="flex items-center gap-1.5">
              <span className="text-[10px] text-text-dim truncate max-w-[80px]">{profiles[pid]?.displayName}</span>
              <DecisionBadge decision={item.profileScores[pid]?.decision} size="xs" />
            </div>
          ))}
        </div>
        <div className="flex-shrink-0 mt-1 text-text-dim">
          {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </div>
      </button>

      {expanded && (
        <div
          className="border-t border-border/60 p-3 grid gap-3"
          style={{ gridTemplateColumns: `repeat(${profileIds.length}, 1fr)` }}
        >
          {profileIds.map((pid) => {
            const score = item.profileScores[pid];
            const reasoning = score?.reasoning || [];
            return (
              <div key={pid} className="space-y-1">
                <div className="flex items-center gap-1.5 mb-2">
                  <DecisionBadge decision={score?.decision} size="xs" />
                  <span className="text-xs text-text-secondary">{profiles[pid]?.displayName}</span>
                </div>
                <div className="space-y-0.5">
                  {reasoning.map((line, i) => {
                    const isFinal = line.includes("החלטה סופית");
                    return (
                      <p
                        key={i}
                        className={cn(
                          "text-xs leading-relaxed",
                          isFinal ? "text-foreground font-medium" : "text-text-dim"
                        )}
                      >
                        {i + 1}. {line}
                      </p>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function ProfileComparisonTable({ items, profiles }) {
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <ComparisonRow key={item.id} item={item} profiles={profiles} />
      ))}
    </div>
  );
}
