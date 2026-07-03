// Visual treatment for each `classified_by` provenance value shown in the
// Debug and LLM QA consoles. Tokenised so the whole console reads as one system.
export const CLASSIFIED_BY_CONFIG = {
  rules: "bg-surface-3 text-text-secondary border-border",
  llm: "bg-signal-feed/12 text-signal-feed border-signal-feed/30",
  "llm+rules_guardrail": "bg-signal-ai/12 text-signal-ai border-signal-ai/30",
  rules_fallback_after_llm_failure: "bg-signal-hidden/12 text-signal-hidden border-signal-hidden/30",
  rules_fallback_low_confidence: "bg-signal-push/12 text-signal-push border-signal-push/30",
};

const FALLBACK = "bg-surface-3 text-text-secondary border-border";

export function classifiedByClass(value) {
  return CLASSIFIED_BY_CONFIG[value] || FALLBACK;
}
