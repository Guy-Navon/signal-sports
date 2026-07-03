import React from "react";
import { cn } from "@/lib/utils";

const TONE_CLASSES = {
  push: "bg-signal-push",
  high: "bg-signal-high",
  feed: "bg-signal-feed",
  low: "bg-signal-low",
  hidden: "bg-signal-hidden",
  ai: "bg-signal-ai",
  neutral: "bg-text-dim",
};

export default function PulseDot({ tone = "neutral", pulse = false, className = "" }) {
  return (
    <span
      className={cn(
        "inline-block w-1.5 h-1.5 rounded-full flex-shrink-0",
        TONE_CLASSES[tone] || TONE_CLASSES.neutral,
        pulse && "animate-pulse-soft",
        className
      )}
    />
  );
}
