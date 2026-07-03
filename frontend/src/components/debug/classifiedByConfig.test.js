import { describe, it, expect } from "vitest";
import { CLASSIFIED_BY_CONFIG, classifiedByClass } from "./classifiedByConfig";

const KNOWN = [
  "rules",
  "llm",
  "llm+rules_guardrail",
  "rules_fallback_after_llm_failure",
  "rules_fallback_low_confidence",
];

describe("classifiedByConfig", () => {
  it("styles every known classified_by value", () => {
    for (const key of KNOWN) {
      expect(CLASSIFIED_BY_CONFIG[key], key).toBeTruthy();
      expect(classifiedByClass(key), key).toBe(CLASSIFIED_BY_CONFIG[key]);
    }
  });

  it("falls back for unknown values", () => {
    const fallback = classifiedByClass("something_new");
    expect(fallback).toBe(classifiedByClass(undefined));
    expect(fallback).toContain("text-text-secondary");
  });

  it("maps failure to red and low-confidence to gold, distinct from llm blue", () => {
    expect(CLASSIFIED_BY_CONFIG.rules_fallback_after_llm_failure).toContain("signal-hidden");
    expect(CLASSIFIED_BY_CONFIG.rules_fallback_low_confidence).toContain("signal-push");
    expect(CLASSIFIED_BY_CONFIG.llm).toContain("signal-feed");
  });
});
