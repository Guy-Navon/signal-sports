import React, { useState } from "react";
import { ThumbsUp, ThumbsDown, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { useApp } from "@/context/AppContext";

// Quiet feedback affordance. Emits the exact backend action strings
// "more_like_this" / "less_like_this" via addFeedback.
//
// variant="icons" — compact thumb icons (stream rows, briefs)
// variant="text"  — spoken text buttons (lead story, bulletins, editorial)
export default function FeedbackControls({ articleId, variant = "icons", className = "" }) {
  const { addFeedback } = useApp();
  const [given, setGiven] = useState(null);

  function handle(action) {
    addFeedback(articleId, action);
    setGiven(action);
  }

  if (given) {
    return (
      <span className={cn("inline-flex items-center gap-1 text-xs text-text-dim", className)}>
        <Check size={12} className="text-signal-high" />
        נשמר
      </span>
    );
  }

  if (variant === "text") {
    return (
      <div className={cn("flex items-center gap-1 text-xs", className)}>
        <button
          onClick={() => handle("more_like_this")}
          className="px-2 py-1 rounded-md text-text-secondary hover:text-signal-high hover:bg-signal-high/10 transition-colors"
        >
          עוד כמו זה
        </button>
        <span className="text-text-dim" aria-hidden>
          ·
        </span>
        <button
          onClick={() => handle("less_like_this")}
          className="px-2 py-1 rounded-md text-text-secondary hover:text-signal-hidden hover:bg-signal-hidden/10 transition-colors"
        >
          פחות מזה
        </button>
      </div>
    );
  }

  return (
    <div className={cn("flex items-center gap-0.5", className)}>
      <button
        onClick={() => handle("more_like_this")}
        aria-label="יותר כמו זה"
        title="יותר כמו זה"
        className={cn(
          "p-1.5 rounded-md text-text-dim transition-colors",
          "hover:text-signal-high hover:bg-signal-high/10"
        )}
      >
        <ThumbsUp size={14} />
      </button>
      <button
        onClick={() => handle("less_like_this")}
        aria-label="פחות כמו זה"
        title="פחות כמו זה"
        className={cn(
          "p-1.5 rounded-md text-text-dim transition-colors",
          "hover:text-signal-hidden hover:bg-signal-hidden/10"
        )}
      >
        <ThumbsDown size={14} />
      </button>
    </div>
  );
}
