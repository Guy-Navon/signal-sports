import React, { useState } from "react";
import { ChevronDown, Tag } from "lucide-react";
import { cn } from "@/lib/utils";
import SignalStrength from "@/components/signal-ui/SignalStrength";
import { getDecisionConfig } from "@/components/feed/decisionConfig";

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
    <div className="sg-topic">
      <button
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        className="sg-topic__toggle"
      >
        <div className="min-w-0">
          <p className="sg-topic__title">
            <bdi dir="auto">{topic.label}</bdi>
          </p>
          <p className="sg-form-note">{kicker}</p>
        </div>
        <ChevronDown
          size={15}
          className={cn(
            "shrink-0 transition-transform",
            expanded && "rotate-180"
          )}
        />
      </button>

      {expanded && (
        <div className="sg-topic__detail space-y-4">
          {topic.mode === "followed_entities_only" && (
            <p className="sg-form-note">
              נושא זה יציג רק כתבות שמכילות את הישויות שאתה עוקב אחריהן
            </p>
          )}

          {topic.entities && topic.entities.length > 0 && (
            <div>
              <p className="sg-form-heading">
                <Tag size={11} /> ישויות
              </p>
              <div className="sg-form-list">
                {topic.entities.map((e) => (
                  <bdi key={e} dir="auto">{e}</bdi>
                ))}
              </div>
            </div>
          )}

          {topic.eventRules && Object.keys(topic.eventRules).length > 0 && (
            <div>
              <p className="sg-form-heading">כללי אירוע</p>
              <div className="space-y-1">
                {Object.entries(topic.eventRules).map(([eventType, decision]) => (
                  <div
                    key={eventType}
                    className="sg-topic__rule"
                  >
                    <span dir="ltr">{eventType}</span>
                    <span className="sg-topic__decision">{decision !== "hidden" && <SignalStrength decision={decision} />}{getDecisionConfig(decision).label}</span>
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
