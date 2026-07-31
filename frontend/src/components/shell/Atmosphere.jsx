import React from "react";
import { motion, useReducedMotion } from "framer-motion";

// Orbit's product atmosphere: a fixed field of quiet spatial relationships.
// Geometry is static; product-state motion belongs to the feed itself.
export default function Atmosphere() {
  const reduce = useReducedMotion();
  return (
    <motion.div
      aria-hidden
      className="orbit-atmosphere fixed inset-0 -z-10 overflow-hidden pointer-events-none"
      initial={reduce ? { opacity: 1 } : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
    >
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 56% 46% at 64% -8%, hsl(var(--signal-high) / 0.055), transparent 62%)," +
            "radial-gradient(ellipse 48% 42% at 2% 96%, hsl(var(--signal-feed) / 0.04), transparent 66%)",
        }}
      />
      <svg
        viewBox="0 0 1000 800"
        fill="none"
        className="absolute top-[8%] end-[-180px] h-[86%] w-auto text-signal-feed opacity-[0.045]"
      >
        <ellipse cx="570" cy="400" rx="440" ry="295" stroke="currentColor" strokeWidth="1" />
        <ellipse
          cx="570"
          cy="400"
          rx="315"
          ry="205"
          stroke="hsl(var(--signal-high))"
          strokeOpacity="0.65"
          strokeDasharray="3 12"
        />
        <path
          d="M120 540 C315 260 742 225 972 410"
          stroke="currentColor"
          strokeWidth="1"
          strokeDasharray="1 14"
        />
      </svg>
      <div
        className="absolute inset-0 opacity-[0.025] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />
    </motion.div>
  );
}
