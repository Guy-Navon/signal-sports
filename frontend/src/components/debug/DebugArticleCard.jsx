import React, { useState } from "react";
import { Bug, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import DecisionBadge from "@/components/feed/DecisionBadge";
import ClassifiedByBadge from "@/components/debug/ClassifiedByBadge";
import ReasoningTrace from "@/components/debug/ReasoningTrace";
import FactsTracePanel from "@/components/debug/FactsTracePanel";
import ClusterEvidence from "@/components/debug/ClusterEvidence";

function MetaCell({ label, value }) {
  return (
    <div className="bg-surface-2 rounded-lg p-2">
      <div className="text-text-dim mb-0.5">{label}</div>
      <div className="text-text-secondary font-medium truncate" title={value}>{value}</div>
    </div>
  );
}

export default function DebugArticleCard({ item }) {
  const [expanded, setExpanded] = useState(false);
  const decision = item.score?.decision || "hidden";
  const reasoning = item.score?.reasoning || [];
  const isCluster = item.type === "cluster";

  const title = isCluster ? item.clusterTitle : item.title;
  const source = isCluster
    ? (item.sourceDisplayNames || item.sources || []).join(", ")
    : item.sourceDisplayName;

  const metaCells = [
    { label: "ספורט", value: item.sport || "—" },
    { label: "ליגה", value: item.league || "—" },
    { label: "סוג אירוע", value: item.eventType || "—" },
    { label: "חשיבות", value: item.importance || "—" },
    { label: "ביטחון", value: item.confidence ? `${Math.round(item.confidence * 100)}%` : "—" },
    { label: "ישויות", value: (item.entities || []).join(", ") || "—" },
    { label: "נושא תואם", value: item.score?.matchedTopic || "—" },
    { label: "כלל תואם", value: item.score?.matchedRule || "—" },
  ];

  return (
    <div
      className={cn(
        "border rounded-xl overflow-hidden transition-colors",
        decision === "hidden"
          ? "border-signal-hidden/30 bg-signal-hidden/5"
          : decision === "push"
            ? "border-signal-push/25 bg-signal-push/5"
            : "border-border bg-surface-1"
      )}
    >
      <button
        className="w-full text-start p-3 flex items-start justify-between gap-3 hover:bg-surface-2/50 transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <DecisionBadge decision={decision} size="xs" />
            <span className="text-[10px] bg-surface-3 text-text-dim rounded-full px-1.5 py-0.5 border border-border" title="המנוע שיצר את העקבה">
              {item.score?.engine ?? "js-local"}
            </span>
            {isCluster && (
              <span className="text-[10px] bg-surface-3 text-text-secondary rounded-full px-1.5 py-0.5 border border-border">
                קלאסטר
              </span>
            )}
          </div>
          <p className="text-sm text-foreground font-medium leading-snug truncate">{title}</p>
          {item.subtitle && (
            <p className="text-xs text-text-dim mt-0.5 line-clamp-3 leading-snug">{item.subtitle}</p>
          )}
          <p className="text-xs text-text-dim mt-0.5">{source} · {item.sport} · {item.league || "—"}</p>
        </div>
        <div className="flex-shrink-0 mt-0.5 text-text-dim">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border/60 p-3 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {metaCells.map(({ label, value }) => (
              <MetaCell key={label} label={label} value={value} />
            ))}
          </div>

          {item.classifiedBy && (
            <div className="space-y-1.5">
              <p className="text-[10px] text-text-dim font-medium uppercase tracking-wide">סיווג LLM</p>
              <div className="flex items-center gap-2 flex-wrap">
                <ClassifiedByBadge value={item.classifiedBy} />
                {item.classificationProvider && item.classificationProvider !== "rules" && (
                  <span className="text-[10px] text-text-secondary bg-surface-2 border border-border rounded-full px-1.5 py-0.5">
                    {item.classificationProvider}
                  </span>
                )}
                {item.classificationConfidence != null && (
                  <span className="text-[10px] text-text-dim">
                    ביטחון LLM: {Math.round(item.classificationConfidence * 100)}%
                  </span>
                )}
              </div>
              {item.classificationReason && (
                <p className="text-[11px] text-text-dim italic leading-snug">{item.classificationReason}</p>
              )}
            </div>
          )}

          {item.classificationTrace && <FactsTracePanel trace={item.classificationTrace} />}

          <div>
            <p className="text-xs text-text-dim font-medium mb-2 flex items-center gap-1">
              <Bug size={11} />
              שרשרת ההחלטה:
            </p>
            <ReasoningTrace reasoning={reasoning} />
          </div>

          {item.score?.contributions?.length > 0 && (
            <div>
              <p className="text-[10px] text-text-dim font-medium uppercase tracking-wide mb-1">
                תרומות (מנוע v2)
              </p>
              <div className="space-y-0.5">
                {item.score.contributions.map((c, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-x-2 text-[11px] font-mono">
                    <span className="text-text-dim">{c.step}</span>
                    <span className={c.effect === "hidden" || String(c.effect).startsWith("-") ? "text-signal-hidden" : "text-signal-high"}>
                      {c.effect}
                    </span>
                    <span className="text-text-secondary">{c.detail}</span>
                    {/* Provenance (issue #84): which layer wrote the fired entry. */}
                    {c.source && (
                      <span className={cn(
                        "px-1.5 py-px rounded-full border text-[10px] font-sans",
                        c.source === "explicit"
                          ? "border-signal-high/40 text-signal-high"
                          : c.source === "learned"
                            ? "border-signal-ai/40 text-signal-ai"
                            : "border-border text-text-dim",
                      )}>
                        {c.source === "explicit" ? "בחירה מפורשת"
                          : c.source === "learned" ? "נלמד" : "מכויל"}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Story-cluster evidence (#104): representative / displayed / priority /
          suppressed members + rule version. Debug is the only surface that sees
          suppressed members — they never reach the consumer payload. */}
      {isCluster && expanded && <ClusterEvidence item={item} />}
    </div>
  );
}
