import { Zap, TrendingUp, Radio, Waves, EyeOff } from "lucide-react";

// The signal system: each decision level is a "signal strength". Relevance is
// encoded as light intensity (rail + glow), not colored card borders.
// Hebrew labels MUST stay in sync with DECISION_LABELS_HE in src/api/normalizers.js
// (locked by decisionConfig.test.js).
export const DECISION_CONFIG = {
  push: {
    label: "דורש תשומת לב",
    tone: "push",
    icon: Zap,
    // rail on the inline-start edge of the card
    rail: "bg-signal-push",
    railGlow: true,
    badge: "bg-signal-push/15 text-signal-push border-signal-push/30",
    dot: "bg-signal-push",
    title: "text-foreground",
    // signal strength 0..4 for the strength meter
    strength: 4,
  },
  high_feed: {
    label: "חשוב",
    tone: "high",
    icon: TrendingUp,
    rail: "bg-signal-high",
    railGlow: false,
    badge: "bg-signal-high/15 text-signal-high border-signal-high/30",
    dot: "bg-signal-high",
    title: "text-foreground",
    strength: 3,
  },
  feed: {
    label: "רגיל",
    tone: "feed",
    icon: Radio,
    rail: "bg-signal-feed/70",
    railGlow: false,
    badge: "bg-signal-feed/12 text-signal-feed border-signal-feed/25",
    dot: "bg-signal-feed",
    title: "text-foreground",
    strength: 2,
  },
  low_feed: {
    label: "נמוך",
    tone: "low",
    icon: Waves,
    rail: "bg-transparent",
    railGlow: false,
    badge: "bg-surface-3 text-text-secondary border-border",
    dot: "bg-signal-low",
    title: "text-text-secondary",
    strength: 1,
  },
  hidden: {
    label: "מוסתר",
    tone: "hidden",
    icon: EyeOff,
    rail: "bg-transparent",
    railGlow: false,
    badge: "bg-signal-hidden/10 text-signal-hidden border-signal-hidden/25",
    dot: "bg-signal-hidden",
    title: "text-text-dim",
    strength: 0,
  },
};

export function getDecisionConfig(decision) {
  return DECISION_CONFIG[decision] || DECISION_CONFIG.feed;
}

export const DECISION_RANK = { hidden: 0, low_feed: 1, feed: 2, high_feed: 3, push: 4 };
