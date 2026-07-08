/**
 * Issue #35 — Debug facts-trace display model (React Testing Library is not
 * installed in this repo; per convention the pure builder is tested).
 */
import { describe, expect, it } from "vitest";
import { summarizeTrace } from "./FactsTracePanel";

const TRACE = {
  taxonomy_version: 1,
  sport: {
    final: "basketball",
    evidence: [
      { sport: "basketball", source: "title_keyword", weight: 3, detail: "יורוליג" },
    ],
  },
  competitions: {
    primary: "comp:euroleague",
    article: ["comp:ibl"],
    explicit_hits: ["comp:euroleague"],
    dropped: ["comp:la_liga"],
  },
  entities: {
    resolved_ids: ["team:maccabi_tlv_bb"],
    alias_to_id: [{ legacy_name: "Maccabi Tel Aviv Basketball", id: "team:maccabi_tlv_bb" }],
    dropped: ["Maccabi Haifa"],
    rejected_llm_mentions: ["Unknown Club"],
  },
  llm: {
    gate_should_call: true,
    gate_reason: "sport_unknown",
    classified_by: "llm+rules_guardrail",
    proposal: {
      sport: "basketball", league: "EuroLeague", event_type: "signing",
      importance: "high", confidence: 0.9, entities: [], reason: "r",
    },
  },
  conflicts: [
    { field: "sport", rule: "weighted_evidence_override", winner: "basketball" },
  ],
  event: { final: "signing", certainty: "confirmed", validated_after_facts: true, corrected: false },
};

describe("summarizeTrace", () => {
  it("returns null without a trace", () => {
    expect(summarizeTrace(null)).toBeNull();
    expect(summarizeTrace(undefined)).toBeNull();
  });

  it("builds evidence chips with source, sport and detail", () => {
    const m = summarizeTrace(TRACE);
    expect(m.sportEvidence).toEqual(["title_keyword → basketball (יורוליג)"]);
  });

  it("lists explicit competitions with the primary marked", () => {
    const m = summarizeTrace(TRACE);
    expect(m.explicitCompetitions).toEqual(["ראשית: comp:euroleague", "comp:ibl"]);
  });

  it("builds alias→id normalization actions", () => {
    const m = summarizeTrace(TRACE);
    expect(m.aliasHits).toEqual(["Maccabi Tel Aviv Basketball → team:maccabi_tlv_bb"]);
  });

  it("collects dropped competitions, dropped entities and rejected LLM mentions", () => {
    const m = summarizeTrace(TRACE);
    expect(m.rejected).toEqual([
      "תחרות: comp:la_liga",
      "ישות: Maccabi Haifa",
      "אזכור LLM: Unknown Club",
    ]);
  });

  it("labels the gate decision with 'why called'", () => {
    const m = summarizeTrace(TRACE);
    expect(m.gate.label).toBe("נקרא — סיבה: sport_unknown");
    expect(m.gate.classifiedBy).toBe("llm+rules_guardrail");
    expect(m.gate.proposal.event_type).toBe("signing");
  });

  it("labels a gated skip", () => {
    const m = summarizeTrace({
      ...TRACE,
      llm: { gate_should_call: false, gate_reason: "deterministic_accept", classified_by: "rules" },
    });
    expect(m.gate.label).toBe("דולג — סיבה: deterministic_accept");
  });

  it("formats conflicts as red-panel lines", () => {
    const m = summarizeTrace(TRACE);
    expect(m.conflicts).toEqual(["weighted_evidence_override → basketball"]);
  });

  it("handles a rules-only trace with no llm block", () => {
    const m = summarizeTrace({ ...TRACE, llm: null, conflicts: [] });
    expect(m.gate).toBeNull();
    expect(m.conflicts).toEqual([]);
  });
});
