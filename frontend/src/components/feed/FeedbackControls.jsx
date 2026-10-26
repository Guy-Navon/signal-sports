import React, { useEffect, useRef, useState } from "react";
import { ThumbsUp, ThumbsDown, Check, AlertCircle, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import { useApp } from "@/context/AppContext";
import { feedbackSaveView, runFeedbackSave } from "@/components/feed/feedbackSaveModel";
import { menuDismissAction } from "@/components/feed/menuDismissModel";

// Quiet feedback affordance. Emits the exact backend action strings
// "more_like_this" / "less_like_this" via addFeedback, plus the two-option
// suppression flow (issue #34): "פחות כאלה" is a learned negative signal
// (one click changes nothing durable); "אל תראה לי יותר" creates the
// EXPLICIT scoped never_show override (backend mode only).
//
// Saves are honest (#197): "נשמר" appears only after the server confirmed
// the event; a failed save says "לא נשמר" and offers a retry.
//
// variant="icons" — compact thumb icons (stream rows, briefs)
// variant="text"  — spoken text buttons (lead story, bulletins, editorial)
export default function FeedbackControls({ articleId, variant = "icons", className = "" }) {
  const { addFeedback, neverShowArticle, isBackendMode } = useApp();
  const [status, setStatus] = useState(/** @type {import("./feedbackSaveModel").FeedbackSaveStatus} */ ("idle"));
  const [showSuppress, setShowSuppress] = useState(false);
  // The last save attempted, so a failed one can be retried as-is.
  const lastSave = useRef(/** @type {null | (() => Promise<unknown>)} */ (null));
  const containerRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const triggerRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const firstItemRef = useRef(/** @type {HTMLButtonElement | null} */ (null));

  // The menu closes on Escape (focus back to its button) or a tap outside (D9).
  useEffect(() => {
    if (!showSuppress) return undefined;
    firstItemRef.current?.focus();
    /** @param {KeyboardEvent | PointerEvent} event */
    function onEvent(event) {
      const inside = Boolean(containerRef.current?.contains(/** @type {Node} */ (event.target)));
      const action = menuDismissAction({
        type: event.type === "keydown" ? "keydown" : "pointerdown",
        key: "key" in event ? event.key : undefined,
        inside,
      });
      if (!action.close) return;
      setShowSuppress(false);
      if (action.restoreFocus) triggerRef.current?.focus();
    }
    document.addEventListener("keydown", onEvent);
    document.addEventListener("pointerdown", onEvent);
    return () => {
      document.removeEventListener("keydown", onEvent);
      document.removeEventListener("pointerdown", onEvent);
    };
  }, [showSuppress]);

  function attempt(save) {
    lastSave.current = save;
    setShowSuppress(false);
    runFeedbackSave(save, setStatus);
  }

  const handle = (action) => attempt(() => addFeedback(articleId, action));
  const handleNeverShow = () => attempt(() => neverShowArticle(articleId));

  const view = feedbackSaveView(status);
  if (view) {
    if (view.canRetry) {
      return (
        <span role="alert" className={cn("inline-flex items-center gap-1 text-xs text-signal-hidden", className)}>
          <AlertCircle size={12} aria-hidden />
          {view.label}
          <button
            type="button"
            onClick={() => lastSave.current && attempt(lastSave.current)}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-text-secondary underline underline-offset-4 hover:text-foreground"
          >
            <RotateCcw size={12} aria-hidden />
            נסו שוב
          </button>
        </span>
      );
    }
    return (
      <span
        role="status"
        aria-busy={view.busy || undefined}
        className={cn("inline-flex items-center gap-1 text-xs text-text-dim", className)}
      >
        {view.tone === "ok" && <Check size={12} className="text-signal-high" aria-hidden />}
        {view.label}
      </span>
    );
  }

  const suppressPopover = showSuppress && (
    <div role="menu" className="absolute z-10 mt-1 end-0 bg-surface-2 border border-border rounded-[10px] shadow-lg p-1.5 flex flex-col gap-1 min-w-[170px]">
      <button
        ref={firstItemRef}
        role="menuitem"
        onClick={() => handle("less_like_this")}
        className="text-xs text-start px-2 py-1.5 rounded-md text-text-secondary hover:bg-surface-3 transition-colors"
      >
        פחות כאלה
      </button>
      {isBackendMode && (
        <button
          role="menuitem"
          onClick={handleNeverShow}
          className="text-xs text-start px-2 py-1.5 rounded-md text-signal-hidden hover:bg-signal-hidden/10 transition-colors"
        >
          אל תראה לי יותר כאלה (חסימה)
        </button>
      )}
    </div>
  );

  if (variant === "text") {
    return (
      <div ref={containerRef} className={cn("relative flex items-center gap-1 text-xs", className)}>
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
          ref={triggerRef}
          aria-haspopup="menu"
          aria-expanded={showSuppress}
          onClick={() => setShowSuppress((v) => !v)}
          className="px-2 py-1 rounded-md text-text-secondary hover:text-signal-hidden hover:bg-signal-hidden/10 transition-colors"
        >
          פחות מזה
        </button>
        {suppressPopover}
      </div>
    );
  }

  return (
    <div ref={containerRef} className={cn("relative flex items-center gap-0.5", className)}>
      <button
        onClick={() => handle("more_like_this")}
        aria-label="יותר כמו זה"
        title="יותר כמו זה"
        className={cn(
          "p-1.5 rounded-md text-text-dim transition-colors",
          "inline-flex items-center justify-center",
          "hover:text-signal-high hover:bg-signal-high/10"
        )}
      >
        <ThumbsUp size={14} />
      </button>
      <button
        ref={triggerRef}
        aria-haspopup="menu"
        aria-expanded={showSuppress}
        onClick={() => setShowSuppress((v) => !v)}
        aria-label="פחות כמו זה"
        title="פחות כמו זה"
        className={cn(
          "p-1.5 rounded-md text-text-dim transition-colors",
          "inline-flex items-center justify-center",
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
