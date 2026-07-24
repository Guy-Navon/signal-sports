import React, { useState } from "react";
import { ThumbsUp, ThumbsDown, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { useApp } from "@/context/AppContext";

// Quiet feedback affordance. Emits the exact backend action strings
// "more_like_this" / "less_like_this" via addFeedback, plus the two-option
// suppression flow (issue #34): "פחות כאלה" is a learned negative signal
// (one click changes nothing durable); "אל תראה לי יותר" creates the
// EXPLICIT scoped never_show override (backend mode only).
//
// variant="icons" — compact thumb icons (stream rows, briefs)
// variant="text"  — spoken text buttons (lead story, bulletins, editorial)
export default function FeedbackControls({ articleId, variant = "icons", className = "" }) {
  const { addFeedback, neverShowArticle, isBackendMode } = useApp();
  const [given, setGiven] = useState(null);
  const [showSuppress, setShowSuppress] = useState(false);

  function handle(action) {
    addFeedback(articleId, action);
    setGiven(action);
    setShowSuppress(false);
  }

  async function handleNeverShow() {
    await neverShowArticle?.(articleId);
    setGiven("never_show");
    setShowSuppress(false);
  }

  if (given) {
    return (
      <span className={cn("inline-flex items-center gap-1 text-xs text-text-dim", className)}>
        <Check size={12} className="text-signal-high" />
        נשמר
      </span>
    );
  }

  const suppressPopover = showSuppress && (
    <div className="absolute end-0 z-10 mt-1 flex min-w-[180px] flex-col gap-1 border border-foreground/25 bg-popover p-1.5 shadow-lg">
      <button
        onClick={() => handle("less_like_this")}
        className="px-2 py-1.5 text-start text-xs text-text-secondary transition-colors hover:bg-surface-3"
      >
        פחות כאלה
      </button>
      {isBackendMode && (
        <button
          onClick={handleNeverShow}
          className="px-2 py-1.5 text-start text-xs text-signal-hidden transition-colors hover:bg-signal-hidden/10"
        >
          אל תראה לי יותר כאלה (חסימה)
        </button>
      )}
    </div>
  );

  if (variant === "text") {
    return (
      <div className={cn("relative flex items-center gap-1 text-xs", className)}>
        <button
          onClick={() => handle("more_like_this")}
          className="border-b border-transparent px-2 py-1 text-text-secondary transition-colors hover:border-signal-high hover:text-signal-high"
        >
          עוד כמו זה
        </button>
        <span className="text-text-dim" aria-hidden>
          ·
        </span>
        <button
          onClick={() => setShowSuppress((v) => !v)}
          className="border-b border-transparent px-2 py-1 text-text-secondary transition-colors hover:border-signal-hidden hover:text-signal-hidden"
        >
          פחות מזה
        </button>
        {suppressPopover}
      </div>
    );
  }

  return (
    <div className={cn("relative flex items-center gap-0.5", className)}>
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
        onClick={() => setShowSuppress((v) => !v)}
        aria-label="פחות כמו זה"
        title="פחות כמו זה"
        className={cn(
          "p-1.5 rounded-md text-text-dim transition-colors",
          "hover:text-signal-hidden hover:bg-signal-hidden/10",
          showSuppress && "text-signal-hidden bg-signal-hidden/10"
        )}
      >
        <ThumbsDown size={14} />
      </button>
      {suppressPopover}
    </div>
  );
}
