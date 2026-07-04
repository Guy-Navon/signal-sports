import React, { useState } from "react";
import { FlaskConical, AlertCircle, CheckCircle2, XCircle } from "lucide-react";
import { runLlmGatingBenchmark } from "@/api/client";
import { formatMs, formatDuration, formatPercent } from "@/api/normalizers";
import { cn } from "@/lib/utils";
import SectionCard from "@/components/shared/SectionCard";
import MonoValue from "@/components/shared/MonoValue";
import { consoleButton, consoleAlert } from "@/components/ops/consoleStyles";

// ── Sub-components ────────────────────────────────────────────────────────────

function FallbackRow({ fallbacks }) {
  if (!fallbacks) return <span className="text-text-dim">—</span>;
  const { connect_error = 0, timeout_or_parse = 0, low_confidence = 0 } = fallbacks;
  return (
    <span className="text-text-secondary">
      connect {connect_error} | timeout/parse {timeout_or_parse} | low conf {low_confidence}
    </span>
  );
}

function ReasonMap({ map, emptyLabel = "—" }) {
  if (!map || Object.keys(map).length === 0) return <span className="text-text-dim">{emptyLabel}</span>;
  return (
    <span className="text-text-secondary">
      {Object.entries(map)
        .sort(([, a], [, b]) => b - a)
        .map(([k, v]) => `${k}: ${v}`)
        .join(" | ")}
    </span>
  );
}

function StatLine({ label, children }) {
  return (
    <div>
      <span className="text-text-dim">{label}: </span>
      {children}
    </div>
  );
}

function SourceBaselineBlock({ sourceId, stats }) {
  if (!stats) return null;
  return (
    <div className="space-y-0.5 text-xs">
      <div className="font-medium text-text-secondary mt-2">{sourceId}:</div>
      <StatLine label="total_ms"><MonoValue className="text-text-secondary">{formatDuration(stats.total_ms)}</MonoValue></StatLine>
      <StatLine label="llm_attempts"><MonoValue className="text-text-secondary">{stats.llm_attempts}</MonoValue></StatLine>
      <StatLine label="llm_successes"><MonoValue className="text-text-secondary">{stats.llm_successes}</MonoValue></StatLine>
      <StatLine label="llm_avg_ms"><MonoValue className="text-text-secondary">{formatMs(stats.llm_avg_ms)}</MonoValue></StatLine>
      <StatLine label="llm_p95_ms"><MonoValue className="text-text-secondary">{formatMs(stats.llm_p95_ms)}</MonoValue></StatLine>
      <StatLine label="fallbacks"><FallbackRow fallbacks={stats.fallbacks} /></StatLine>
      <StatLine label="sport_unknown">
        <MonoValue className={stats.sport_unknown > 0 ? "text-signal-push" : "text-text-secondary"}>{stats.sport_unknown}</MonoValue>
      </StatLine>
    </div>
  );
}

function SourceGatedBlock({ sourceId, stats }) {
  if (!stats) return null;
  return (
    <div className="space-y-0.5 text-xs">
      <div className="font-medium text-text-secondary mt-2">{sourceId}:</div>
      <StatLine label="total_ms"><MonoValue className="text-text-secondary">{formatDuration(stats.total_ms)}</MonoValue></StatLine>
      <StatLine label="llm_attempts"><MonoValue className="text-text-secondary">{stats.llm_attempts}</MonoValue></StatLine>
      <StatLine label="llm_skipped"><MonoValue className="text-text-secondary">{stats.llm_skipped}</MonoValue></StatLine>
      <StatLine label="skip_rate"><MonoValue className="text-text-secondary">{formatPercent(stats.skip_rate)}</MonoValue></StatLine>
      <StatLine label="llm_avg_ms"><MonoValue className="text-text-secondary">{formatMs(stats.llm_avg_ms)}</MonoValue></StatLine>
      <StatLine label="llm_p95_ms"><MonoValue className="text-text-secondary">{formatMs(stats.llm_p95_ms)}</MonoValue></StatLine>
      <StatLine label="fallbacks"><FallbackRow fallbacks={stats.fallbacks} /></StatLine>
      <StatLine label="llm_skip_reasons"><ReasonMap map={stats.llm_skip_reasons} /></StatLine>
      <StatLine label="llm_call_reasons"><ReasonMap map={stats.llm_call_reasons} /></StatLine>
      <StatLine label="sport_unknown">
        <MonoValue className={stats.sport_unknown > 0 ? "text-signal-push" : "text-text-secondary"}>{stats.sport_unknown}</MonoValue>
      </StatLine>
    </div>
  );
}

function ComparisonRow({ sourceId, comp }) {
  if (!comp) return null;
  const delta = comp.sport_unknown_delta;
  const deltaStr = delta === 0 ? "Δ 0" : delta > 0 ? `Δ +${delta}` : `Δ ${delta}`;
  return (
    <div className={cn(
      "flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs px-3 py-2 rounded-[10px] border",
      comp.passes_targets
        ? "border-signal-high/30 bg-signal-high/5"
        : "border-signal-push/30 bg-signal-push/5"
    )}>
      <span className="font-medium text-text-secondary">{sourceId}:</span>
      <span className="text-text-dim">saved <MonoValue className="text-text-secondary">{comp.llm_call_reduction}</MonoValue> LLM calls</span>
      <span className="text-text-dim">|</span>
      <span className="text-text-dim">skip <MonoValue className="text-text-secondary">{formatPercent(comp.skip_rate)}</MonoValue></span>
      <span className="text-text-dim">|</span>
      <span className="text-text-dim">time saved <MonoValue className="text-text-secondary">{formatDuration(comp.total_ms_reduction)}</MonoValue></span>
      <span className="text-text-dim">|</span>
      <span className="text-text-dim">sport_unknown <MonoValue className={delta > 0 ? "text-signal-push" : "text-text-secondary"}>{deltaStr}</MonoValue></span>
      <span className="text-text-dim">|</span>
      {comp.passes_targets ? (
        <span className="flex items-center gap-1 text-signal-high font-medium"><CheckCircle2 size={11} /> PASS</span>
      ) : (
        <span className="flex items-center gap-1 text-signal-push font-medium"><XCircle size={11} /> FAIL</span>
      )}
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div className="font-semibold text-text-secondary border-b border-border pb-1 mb-2">{children}</div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function BenchmarkPanel({ isBackendMode }) {
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  if (!isBackendMode) return null;

  const handleRun = async () => {
    setIsRunning(true);
    setResult(null);
    setError(null);
    try {
      const data = await runLlmGatingBenchmark();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsRunning(false);
    }
  };

  const sources = result?.sources ?? [];

  return (
    <SectionCard title="בנצ׳מרק LLM Gating" icon={FlaskConical}>
      <div className="space-y-3" data-testid="gating-benchmark-panel">
        <p className="text-xs text-signal-push/80">
          כלי QA מקומי — מוחק ומייבא מחדש כתבות RSS. דורש ALLOW_DEV_RESET=true ו־CLASSIFICATION_PROVIDER=ollama.
        </p>

        <button
          onClick={handleRun}
          disabled={isRunning}
          className={consoleButton("ghost")}
          data-testid="benchmark-run-button"
        >
          <FlaskConical size={12} />
          {isRunning ? "מריץ בנצ׳מרק... (עלול לקחת 15–20 דקות)" : "הרץ בנצ׳מרק מלא"}
        </button>

        {isRunning && (
          <p className="text-xs text-text-dim" data-testid="benchmark-loading">
            שלב 1: baseline — מריץ ייבוא ללא gating (כל כתבה קוראת ל־LLM).<br />
            שלב 2: gated — מריץ ייבוא עם gating פעיל.<br />
            הסבלנות תוגמל בנתונים.
          </p>
        )}

        {error && (
          <div className={consoleAlert("error")} data-testid="benchmark-error">
            <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {result && (
          <div className="space-y-4 text-xs" data-testid="benchmark-result">
            <div className="text-text-dim text-[10px]">
              provider: <span className="text-text-secondary">{result.provider}</span>
            </div>

            <div>
              <SectionLabel>Baseline — gating disabled:</SectionLabel>
              {sources.map((src) => (
                <SourceBaselineBlock key={src} sourceId={src} stats={result.baseline?.sources?.[src]} />
              ))}
            </div>

            <div>
              <SectionLabel>Gating enabled:</SectionLabel>
              {sources.map((src) => (
                <SourceGatedBlock key={src} sourceId={src} stats={result.gated?.sources?.[src]} />
              ))}
            </div>

            <div>
              <SectionLabel>השוואה:</SectionLabel>
              <div className="space-y-2">
                {sources.map((src) =>
                  result.comparison?.[src] ? (
                    <ComparisonRow key={src} sourceId={src} comp={result.comparison[src]} />
                  ) : null
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </SectionCard>
  );
}
