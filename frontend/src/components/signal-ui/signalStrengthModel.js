import { getDecisionConfig } from "@/components/feed/decisionConfig";

// The signal strength mark of the new consumer UI (#462): three slanted strokes,
// filled by decision. Derived from DECISION_CONFIG.strength (hidden 0 .. push 4)
// so the ranking is declared once: the mark has three strokes, so push fills the
// same three as high_feed and is told apart by the alert colour instead.
export const SIGNAL_STROKES = 3;

const PUSH_STRENGTH = 4;

export function signalStrength(decision) {
  const config = getDecisionConfig(decision);
  return {
    filled: Math.min(config.strength, SIGNAL_STROKES),
    alert: config.strength >= PUSH_STRENGTH,
    label: `עוצמת סיגנל: ${config.label}`,
  };
}
