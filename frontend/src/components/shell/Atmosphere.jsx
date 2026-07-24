import React from "react";

// A restrained registration mark for the publication canvas. The grid and
// colour fields live in the shell CSS; this is the only decorative object.
export default function Atmosphere() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed start-0 top-1/2 z-0 hidden -translate-y-1/2 items-center gap-2 xl:flex [writing-mode:vertical-rl]"
    >
      <span className="h-14 w-px bg-foreground/25" />
      <span className="font-mono text-[8px] font-bold tracking-[0.28em] text-foreground/30">
        SIGNAL SPORTS / LIVE DESK
      </span>
      <span className="h-6 w-px bg-signal-push/60" />
    </div>
  );
}
