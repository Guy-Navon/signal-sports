// Presentation only: affinity values and inference stay backend-owned. Reuse
// the shared decision mark rather than defining another stroke/rank scale.
const SIGNAL_BY_AFFINITY = { "-1": "low_feed", 0: "feed", 1: "high_feed", 2: "push" };

export function affinitySignal(level) {
  return SIGNAL_BY_AFFINITY[level] ?? null;
}
