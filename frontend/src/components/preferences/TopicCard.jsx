import React, { useState } from "react";
import { ChevronDown, Tag } from "lucide-react";
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

// A topic as a quiet, expandable row — kicker line (priority · mode · leagues)
// instead of a pile of separate badges, matching the Feed's storytelling.
export default function TopicCard({ topic }) {
  const [expanded, setExpanded] = useState(false);
  const modeLabel = MODE_LABELS[topic.mode] || topic.mode;
  const kicker = [`עדיפות ${topic.priority}`, modeLabel, topic.leagues?.join(", ")]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="border-b border-border/60 last:border-0">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full text-start py-3.5 flex items-start justify-between gap-3 group"
      >
        <div className="min-w-0">
          <p className="font-medium text-foreground text-sm group-hover:text-signal-high transition-colors">
            {topic.label}
          </p>
          <p className="text-xs text-text-dim mt-0.5">{kicker}</p>
        </div>
        <ChevronDown
          size={15}
          className={cn(
            "text-text-dim flex-shrink-0 mt-0.5 transition-transform",
            expanded && "rotate-180"
          )}
        />
      </button>

      {expanded && (
        <div className="pb-4 ps-0.5 space-y-4">
          {topic.mode === "followed_entities_only" && (
            <p className="text-xs text-signal-ai/90">
              נושא זה יציג רק כתבות שמכילות את הישויות שאתה עוקב אחריהן
            </p>
          )}

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
                    className="flex items-center justify-between py-1 border-b border-border/40 last:border-0"
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
