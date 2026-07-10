import React from "react";
import SignalMark from "@/components/shell/SignalMark";

// Shared stage for the auth pages (User Platform PR 3, #51). Login/signup are
// PRODUCT experiences: they render outside both AppShell groups (PageNotFound
// precedent) and carry their own quiet atmosphere in the product's editorial
// language — mesh glow, court-line whisper, SignalMark — never console styling.
export default function AuthScene({ kicker, title, children }) {
  return (
    <div
      dir="rtl"
      className="relative min-h-screen flex items-center justify-center p-6 overflow-hidden bg-background"
    >
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 55% 45% at 50% 30%, hsl(var(--signal-high) / 0.07), transparent 65%)",
        }}
      />
      <svg
        aria-hidden
        viewBox="0 0 600 600"
        fill="none"
        className="absolute inset-0 m-auto h-[130%] w-auto text-foreground opacity-[0.03]"
      >
        <circle cx="300" cy="300" r="260" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="300" cy="300" r="160" stroke="currentColor" strokeWidth="1" />
      </svg>

      <div className="relative w-full max-w-sm">
        <div className="flex items-center justify-center gap-2 mb-8">
          <SignalMark />
          <span className="font-display font-bold text-foreground text-xl tracking-tight">
            סיגנל
          </span>
        </div>

        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-signal-ai mb-2 text-center">
          {kicker}
        </p>
        <h1 className="font-display text-2xl font-bold text-foreground text-center mb-8">
          {title}
        </h1>

        {children}
      </div>
    </div>
  );
}
