import React from "react";
import SignalStrength from "@/components/signal-ui/SignalStrength";
import { LEVEL_LABELS } from "@/components/interests/interestsModel";
import { affinitySignal } from "./affinitySignal";

export default function AffinityLevel({ level }) {
  const decision = affinitySignal(level);
  return (
    <span className="sg-affinity-level">
      {/* The adjacent preference label is the accessible name. A preference
          strength is not itself a feed delivery decision. */}
      {decision && <span aria-hidden="true"><SignalStrength decision={decision} /></span>}
      <span>{LEVEL_LABELS[level] ?? level}</span>
    </span>
  );
}
