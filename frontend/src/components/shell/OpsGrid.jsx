import React from "react";
import { motion, useReducedMotion } from "framer-motion";

// The console's backdrop: a flat blueprint grid instead of the product's
// floodlit atmosphere — instrument-panel energy, not editorial. Fades in on
// mount so crossing from the product into the console is felt, not just
// clicked. Steel-blue tint matches the console's action colour.
export default function OpsGrid() {
  const reduce = useReducedMotion();
  return (
    <motion.div
      aria-hidden
      className="fixed inset-0 -z-10 overflow-hidden pointer-events-none"
      initial={reduce ? { opacity: 1 } : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
    >
      <div
        className="absolute inset-0 opacity-[0.05]"
        style={{
          backgroundImage:
            "linear-gradient(hsl(var(--signal-feed)) 1px, transparent 1px)," +
            "linear-gradient(90deg, hsl(var(--signal-feed)) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 70% 50% at 100% 0%, hsl(var(--signal-feed) / 0.05), transparent 65%)",
        }}
      />
    </motion.div>
  );
}
