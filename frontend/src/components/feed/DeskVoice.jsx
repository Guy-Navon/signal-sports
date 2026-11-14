import React from "react";
import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { deskVoiceView } from "@/components/feed/deskVoiceModel";

// Consumer explanations are reader sentences for every role. Engine traces
// remain reachable in Debug and never replace the reader's explanation here.
export default function DeskVoice({ reason = null, variant = "line", className = "" }) {
  const view = deskVoiceView({ reason });
  if (!view) return null;
  const isFull = variant === "full";
  return (
    <p className={cn("flex items-center gap-1.5 min-w-0", isFull ? "text-sm" : "text-xs", className)}>
      <Sparkles size={isFull ? 14 : 12} className="text-signal-ai flex-shrink-0" aria-hidden />
      <span className={cn("line-clamp-2 break-words", isFull ? "text-text-secondary" : "text-text-dim")}>
        {isFull && <span className="text-signal-ai/90 font-medium">למה אצלך: </span>}
        {view.text}
      </span>
    </p>
  );
}
