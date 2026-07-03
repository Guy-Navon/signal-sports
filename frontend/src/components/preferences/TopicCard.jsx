import React, { useState } from "react";
import { ChevronDown, ChevronUp, Tag } from "lucide-react";
import { cn } from "@/lib/utils";
import DecisionBadge from "@/components/feed/DecisionBadge";
import GhostChip from "@/components/shared/GhostChip";

const MODE_LABELS = {
  all: "הכל — כל הכתבות",
  major_only: "חשוב בלבד — רק כתבות משמעותיות",
  followed_entities_only: "ישויות בלבד — רק ישויות שאני עוקב אחריהן",
  muted: "מושתק",
  titles_only: "כותרות בלבד — רק ז׳אנרים ספציפיים",
  high_importance_only: "חשיבות גבוהה בלבד",
};

export default function TopicCard({ topic }) {
  const [expanded, setExpanded] = useState(false);
  const modeLabel = MODE_LABELS[topic.mode] || topic.mode;

  return (
    <div className="border border-border rounded-2xl overflow-hidden bg-surface-1">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full text-start p-4 flex items-start justify-between gap-3 hover:bg-surface-2/50 transition-colors"
      >
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="font-medium text-foreground text-sm">{topic.label}</span>
            <span className="text-[10px] bg-surface-3 border border-border rounded-full px-2 py-0.5 text-text-secondary">
              עדיפות: {topic.priority}
            </span>
          </div>
          <p className="text-xs text-text-dim">{modeLabel}</p>
          {topic.leagues && topic.leagues.length > 0 && (
            <p className="text-xs text-text-dim mt-0.5">ליגות: {topic.leagues.join(", ")}</p>
          )}
        </div>
        <span className="text-text-dim mt-1 flex-shrink-0">
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-border p-4 space-y-4">
          <div className="bg-surface-2 rounded-lg p-3">
            <p className="text-xs text-text-secondary">
              <span className="text-foreground font-medium">מצב: </span>
              {modeLabel}
            </p>
            {topic.mode === "followed_entities_only" && (
              <p className="text-xs text-signal-push/90 mt-1">
                ⚠️ נושא זה יציג רק כתבות שמכילות את הישויות שאתה עוקב אחריהן
              </p>
            )}
          </div>

          {topic.entities && topic.entities.length > 0 && (
            <div>
              <p className="text-xs text-text-dim mb-2 flex items-center gap-1">
                <Tag size={11} /> ישויות
              </p>
              <div className="flex flex-wrap gap-1.5">
                {topic.entities.map((e) => (
                  <GhostChip key={e}>{e}</GhostChip>
                ))}
              </div>
            </div>
          )}

          {topic.eventRules && Object.keys(topic.eventRules).length > 0 && (
            <div>
              <p className="text-xs text-text-dim mb-2">כללי אירוע</p>
              <div className="space-y-1">
                {Object.entries(topic.eventRules).map(([eventType, decision]) => (
                  <div
                    key={eventType}
                    className={cn("flex items-center justify-between py-1 border-b border-border/50")}
                  >
                    <span className="text-xs text-text-secondary font-mono">{eventType}</span>
                    <DecisionBadge decision={decision} size="xs" />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
