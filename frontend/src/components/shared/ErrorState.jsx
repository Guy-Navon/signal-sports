import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

// variant="strip" — thin banner (e.g. backend connection error under the header).
// variant="page" — centered full-area error.
export default function ErrorState({
  variant = "strip",
  title,
  message = null,
  hint = null,
  onRetry = null,
  retryLabel = "נסה שוב",
  className = "",
}) {
  if (variant === "page") {
    return (
      <div className={cn("flex flex-col items-center justify-center text-center py-16 px-4", className)}>
        <div className="w-12 h-12 rounded-full bg-signal-hidden/10 border border-signal-hidden/30 flex items-center justify-center mb-4">
          <AlertCircle size={20} className="text-signal-hidden" />
        </div>
        <p className="text-base font-medium text-foreground">{title}</p>
        {message && <p className="text-sm text-text-secondary mt-1 max-w-md break-words">{message}</p>}
        {hint && <p className="text-xs text-text-dim mt-2">{hint}</p>}
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-4 flex items-center gap-1.5 text-sm text-foreground bg-surface-2 hover:bg-surface-3 border border-border rounded-lg px-3 py-1.5 transition-colors"
          >
            <RefreshCw size={13} />
            {retryLabel}
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "bg-signal-hidden/10 border-b border-signal-hidden/25 px-4 py-2 flex items-center justify-between gap-4",
        className
      )}
    >
      <div className="flex items-center gap-2 min-w-0">
        <AlertCircle size={13} className="text-signal-hidden flex-shrink-0" />
        <span className="text-signal-hidden text-xs font-medium flex-shrink-0">{title}</span>
        {message && <span className="text-signal-hidden/70 text-xs truncate">{message}</span>}
      </div>
      <div className="flex items-center gap-3 flex-shrink-0">
        {hint && <span className="text-signal-hidden/60 text-[10px] hidden sm:inline">{hint}</span>}
        {onRetry && (
          <button
            onClick={onRetry}
            className="flex items-center gap-1 text-xs text-signal-hidden hover:text-foreground bg-signal-hidden/10 hover:bg-signal-hidden/20 border border-signal-hidden/30 rounded px-2 py-0.5 transition-colors"
          >
            <RefreshCw size={10} />
            {retryLabel}
          </button>
        )}
      </div>
    </div>
  );
}
