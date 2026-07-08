import React from "react";
import { AlertTriangle } from "lucide-react";

/**
 * ArticleFacts trace panels (issue #35): deterministic evidence, competition
 * evidence, entity normalization actions, the LLM gate decision ("why
 * called"), event validation, and a red conflicts panel — all read from the
 * persisted classification_trace, so a full raw-input → final-facts chain is
 * visible without reading code. Backend-mode rows only (local mock articles
 * carry no trace).
 */

function Chips({ label, values, tone = "" }) {
  if (!values || values.length === 0) return null;
  return (
    <div>
      <div className="text-[10px] text-text-dim mb-1">{label}</div>
      <div className="flex flex-wrap gap-1">
        {values.map((v, i) => (
          <span
            key={i}
            className={
              "px-1.5 py-0.5 rounded-full border text-[10px] " +
              (tone || "border-border bg-surface-2 text-text-secondary")
            }
          >
            {v}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Pure display-model builder — exported for tests (no RTL in this repo). */
export function summarizeTrace(trace) {
  if (!trace) return null;
  const comps = trace.competitions ?? {};
  const entities = trace.entities ?? {};
  const llm = trace.llm ?? null;
  return {
    taxonomyVersion: trace.taxonomy_version,
    // Evidence items: {sport, source, weight, detail}
    sportEvidence: (trace.sport?.evidence ?? []).map(
      (e) => `${e.source ?? "?"} → ${e.sport ?? "?"}${e.detail ? ` (${e.detail})` : ""}`
    ),
    explicitCompetitions: [
      ...(comps.primary ? [`ראשית: ${comps.primary}`] : []),
      ...(comps.article ?? []),
    ],
    aliasHits: (entities.alias_to_id ?? []).map((m) => `${m.legacy_name} → ${m.id}`),
    rejected: [
      ...(comps.dropped ?? []).map((d) => `תחרות: ${typeof d === "string" ? d : d.id ?? JSON.stringify(d)}`),
      ...(entities.dropped ?? []).map((d) => `ישות: ${typeof d === "string" ? d : d.name ?? JSON.stringify(d)}`),
      ...(entities.rejected_llm_mentions ?? []).map((m) => `אזכור LLM: ${m}`),
    ],
    gate: llm && {
      label: llm.gate_should_call
        ? `נקרא — סיבה: ${llm.gate_reason ?? "—"}`
        : `דולג — סיבה: ${llm.gate_reason ?? "—"}`,
      classifiedBy: llm.classified_by ?? null,
      proposal: llm.proposal ?? null,
    },
    event: trace.event ?? {},
    conflicts: (trace.conflicts ?? []).map((c) =>
      `${c.rule ?? "?"}${c.winner ? ` → ${c.winner}` : ""}${c.dropped ? ` (הוסר: ${JSON.stringify(c.dropped)})` : ""}`
    ),
  };
}

export default function FactsTracePanel({ trace }) {
  const model = summarizeTrace(trace);
  if (!model) return null;

  const { sportEvidence, aliasHits, conflicts } = model;
  const event = model.event;
  const llm = model.gate;

  return (
    <div className="space-y-3" data-testid="facts-trace">
      <p className="text-[10px] text-text-dim font-medium uppercase tracking-wide">
        עקבות סיווג (ArticleFacts · taxonomy v{model.taxonomyVersion})
      </p>

      <div className="grid sm:grid-cols-2 gap-3 text-xs">
        <Chips label="ראיות ספורט" values={sportEvidence} />
        <Chips label="תחרויות מפורשות" values={model.explicitCompetitions} />
        <Chips label="ישויות (alias → id)" values={aliasHits} />
        <Chips
          label="הוסרו / נדחו"
          values={model.rejected}
          tone="border-signal-hidden/40 bg-signal-hidden/5 text-text-secondary"
        />
      </div>

      {llm && (
        <div className="text-xs bg-surface-2 border border-border rounded-[10px] p-2 space-y-1">
          <div className="text-[10px] text-text-dim font-medium">שער LLM</div>
          <div className="text-text-secondary">
            {llm.label}
            {" · "}
            <span className="text-text-dim">{llm.classifiedBy}</span>
          </div>
          {llm.proposal && (
            <div className="text-text-dim">
              הצעה: {llm.proposal.sport}/{llm.proposal.league ?? "—"} ·{" "}
              {llm.proposal.event_type} · ביטחון{" "}
              {Math.round((llm.proposal.confidence ?? 0) * 100)}%
            </div>
          )}
        </div>
      )}

      {event.validated_after_facts && (
        <div className="text-[11px] text-text-dim">
          אימות אירוע: {event.final} ({event.certainty})
          {event.corrected && (
            <span className="text-signal-push/90"> · תוקן ל-news (ראיות לא מספקות)</span>
          )}
        </div>
      )}

      {conflicts.length > 0 && (
        <div
          className="bg-signal-push/5 border border-signal-push/30 rounded-[10px] p-2 space-y-1"
          data-testid="conflicts-panel"
        >
          <div className="flex items-center gap-1 text-[10px] text-signal-push font-medium">
            <AlertTriangle size={11} /> קונפליקטים ({conflicts.length})
          </div>
          {conflicts.map((c, i) => (
            <div key={i} className="text-[11px] text-text-secondary font-mono">
              {c}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
