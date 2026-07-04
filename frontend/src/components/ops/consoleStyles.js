import { cn } from "@/lib/utils";

// Shared console-area styling recipes so every ops panel reads as one system.
// Steel-blue (signal-feed) is the neutral console action colour; the product's
// green is reserved for the consumer feed.

export function consoleButton(variant = "primary", className = "") {
  const base =
    "inline-flex items-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";
  const variants = {
    primary:
      "px-4 py-2 bg-signal-feed/15 border border-signal-feed/30 text-signal-feed hover:bg-signal-feed/25",
    ghost:
      "px-3 py-1.5 text-xs border border-border text-text-secondary hover:text-foreground hover:border-text-dim",
    danger:
      "px-4 py-2 bg-signal-hidden/10 border border-signal-hidden/30 text-signal-hidden hover:bg-signal-hidden/20",
  };
  return cn(base, variants[variant] || variants.primary, className);
}

// Small pill toggle used for source enable/disable (RTL-safe, no Radix translate).
export function consoleToggle(enabled, className = "") {
  return cn(
    "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors disabled:cursor-not-allowed disabled:opacity-50",
    enabled
      ? "bg-signal-high/10 border-signal-high/30 text-signal-high hover:bg-signal-high/20"
      : "bg-surface-3 border-border text-text-dim hover:text-text-secondary",
    className
  );
}

export function consoleAlert(tone = "warn", className = "") {
  const tones = {
    warn: "text-signal-push bg-signal-push/10 border-signal-push/25",
    error: "text-signal-hidden bg-signal-hidden/10 border-signal-hidden/25",
  };
  return cn(
    "flex items-start gap-2 text-xs rounded-lg px-3 py-2 border",
    tones[tone] || tones.warn,
    className
  );
}
