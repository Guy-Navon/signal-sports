import React from "react";
import { Zap, TrendingUp, Minus, Eye, EyeOff } from "lucide-react";

const BADGE_CONFIG = {
  push: {
    label: "דורש תשומת לב",
    bg: "bg-amber-500/20",
    border: "border-amber-500/50",
    text: "text-amber-300",
    dot: "bg-amber-400",
    icon: Zap
  },
  high_feed: {
    label: "חשוב",
    bg: "bg-emerald-500/20",
    border: "border-emerald-500/40",
    text: "text-emerald-300",
    dot: "bg-emerald-400",
    icon: TrendingUp
  },
  feed: {
    label: "רגיל",
    bg: "bg-blue-500/15",
    border: "border-blue-500/30",
    text: "text-blue-300",
    dot: "bg-blue-400",
    icon: Minus
  },
  low_feed: {
    label: "נמוך",
    bg: "bg-gray-700/50",
    border: "border-gray-600/50",
    text: "text-gray-400",
    dot: "bg-gray-500",
    icon: Eye
  },
  hidden: {
    label: "מוסתר",
    bg: "bg-red-500/10",
    border: "border-red-500/30",
    text: "text-red-400",
    dot: "bg-red-500",
    icon: EyeOff
  }
};

export default function DecisionBadge({ decision, size = "sm" }) {
  const config = BADGE_CONFIG[decision] || BADGE_CONFIG.feed;
  const Icon = config.icon;

  if (size === "xs") {
    return (
      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border ${config.bg} ${config.border} ${config.text}`}>
        <Icon size={9} />
        {config.label}
      </span>
    );
  }

  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border ${config.bg} ${config.border} ${config.text}`}>
      <Icon size={11} />
      {config.label}
    </span>
  );
}

export { BADGE_CONFIG };