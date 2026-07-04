import React from "react";

// The product canvas's atmosphere: a fixed, decorative backdrop behind every
// product page (not rendered in the ops console — ops stays flat/instrument-
// panel by design). A soft floodlight mesh, one large half-court arc, and a
// whisper of film grain — identity, not decoration. Static positioning +
// opacity-only breathing keep this essentially free at runtime.
export default function Atmosphere() {
  return (
    <div aria-hidden className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 50% -10%, hsl(var(--signal-high) / 0.05), transparent 60%)," +
            "radial-gradient(ellipse 45% 40% at 100% 100%, hsl(var(--signal-ai) / 0.03), transparent 60%)",
        }}
      />
      <svg
        viewBox="0 0 800 800"
        fill="none"
        className="absolute top-1/2 -translate-y-1/2 end-[-220px] h-[140%] w-auto text-foreground opacity-[0.035] rtl:-scale-x-100"
      >
        <circle cx="800" cy="400" r="360" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="800" cy="400" r="230" stroke="currentColor" strokeWidth="1" />
        <path d="M 800 60 A 340 340 0 0 0 800 740" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      <div
        className="absolute inset-0 opacity-[0.025] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />
    </div>
  );
}
