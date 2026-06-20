import React, { useState } from "react";
import { FlaskConical, AlertCircle, CheckCircle2, XCircle } from "lucide-react";
import { runLlmGatingBenchmark } from "@/api/client";
import { formatMs, formatDuration, formatPercent } from "@/api/normalizers";

// ── Sub-components ────────────────────────────────────────────────────────────

function FallbackRow({ fallbacks }) {
  if (!fallbacks) return <span className="text-gray-600">—</span>;
  const { connect_error = 0, timeout_or_parse = 0, low_confidence = 0 } = fallbacks;
  return (
    <span className="text-gray-500">
      connect {connect_error} | timeout/parse {timeout_or_parse} | low conf {low_confidence}
    </span>
  );
}

function ReasonMap({ map, emptyLabel = "—" }) {
  if (!map || Object.keys(map).length === 0) return <span className="text-gray-600">{emptyLabel}</span>;
  return (
    <span className="text-gray-500">
      {Object.entries(map)
        .sort(([, a], [, b]) => b - a)
        .map(([k, v]) => `${k}: ${v}`)
        .join(" | ")}
    </span>
  );
}

function SourceBaselineBlock({ sourceId, stats }) {
  if (!stats) return null;
  return (
    <div className="space-y-0.5 text-xs">
      <div className="font-medium text-gray-400 mt-2">{sourceId}:</div>
      <div>
        <span className="text-gray-600">total_ms: </span>
        <span className="text-gray-300">{formatDuration(stats.total_ms)}</span>
      </div>
      <div>
        <span className="text-gray-600">llm_attempts: </span>
        <span className="text-gray-300">{stats.llm_attempts}</span>
      </div>
      <div>
        <span className="text-gray-600">llm_successes: </span>
        <span className="text-gray-300">{stats.llm_successes}</span>
      </div>
      <div>
        <span className="text-gray-600">llm_avg_ms: </span>
        <span className="text-gray-300">{formatMs(stats.llm_avg_ms)}</span>
      </div>
      <div>
        <span className="text-gray-600">llm_p95_ms: </span>
        <span className="text-gray-300">{formatMs(stats.llm_p95_ms)}</span>
      </div>
      <div>
        <span className="text-gray-600">fallbacks: </span>
        <FallbackRow fallbacks={stats.fallbacks} />
      </div>
      <div>
        <span className="text-gray-600">sport_unknown: </span>
        <span className={stats.sport_unknown > 0 ? "text-amber-400" : "text-gray-300"}>
          {stats.sport_unknown}
        </span>
      </div>
    </div>
  );
}

function SourceGatedBlock({ sourceId, stats }) {
  if (!stats) return null;
  return (
    <div className="space-y-0.5 text-xs">
      <div className="font-medium text-gray-400 mt-2">{sourceId}:</div>
      <div>
        <span className="text-gray-600">total_ms: </span>
        <span className="text-gray-300">{formatDuration(stats.total_ms)}</span>
      </div>
      <div>
        <span className="text-gray-600">llm_attempts: </span>
        <span className="text-gray-300">{stats.llm_attempts}</span>
      </div>
      <div>
        <span className="text-gray-600">llm_skipped: </span>
        <span className="text-gray-300">{stats.llm_skipped}</span>
      </div>
      <div>
        <span className="text-gray-600">skip_rate: </span>
        <span className="text-gray-300">{formatPercent(stats.skip_rate)}</span>
      </div>
      <div>
        <span className="text-gray-600">llm_avg_ms: </span>
        <span className="text-gray-300">{formatMs(stats.llm_avg_ms)}</span>
      </div>
      <div>
        <span className="text-gray-600">llm_p95_ms: </span>
        <span className="text-gray-300">{formatMs(stats.llm_p95_ms)}</span>
      </div>
      <div>
        <span className="text-gray-600">fallbacks: </span>
        <FallbackRow fallbacks={stats.fallbacks} />
      </div>
      <div>
        <span className="text-gray-600">llm_skip_reasons: </span>
        <ReasonMap map={stats.llm_skip_reasons} />
      </div>
      <div>
        <span className="text-gray-600">llm_call_reasons: </span>
        <ReasonMap map={stats.llm_call_reasons} />
      </div>
      <div>
        <span className="text-gray-600">sport_unknown: </span>
        <span className={stats.sport_unknown > 0 ? "text-amber-400" : "text-gray-300"}>
          {stats.sport_unknown}
        </span>
      </div>
    </div>
  );
}

function ComparisonRow({ sourceId, comp }) {
  if (!comp) return null;
  const delta = comp.sport_unknown_delta;
  const deltaStr = delta === 0 ? "Δ 0" : delta > 0 ? `Δ +${delta}` : `Δ ${delta}`;
  return (
    <div className={`flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs px-3 py-2 rounded-lg border ${
      comp.passes_targets
        ? "border-emerald-800/40 bg-emerald-900/10"
        : "border-amber-800/40 bg-amber-900/10"
    }`}>
      <span className="font-medium text-gray-300">{sourceId}:</span>
      <span className="text-gray-500">
        saved <span className="text-gray-300">{comp.llm_call_reduction}</span> LLM calls
      </span>
      <span className="text-gray-700">|</span>
      <span className="text-gray-500">
        skip <span className="text-gray-300">{formatPercent(comp.skip_rate)}</span>
      </span>
      <span className="text-gray-700">|</span>
      <span className="text-gray-500">
        time saved <span className="text-gray-300">{formatDuration(comp.total_ms_reduction)}</span>
      </span>
      <span className="text-gray-700">|</span>
      <span className="text-gray-500">
        sport_unknown <span className={delta > 0 ? "text-amber-400" : "text-gray-300"}>{deltaStr}</span>
      </span>
      <span className="text-gray-700">|</span>
      {comp.passes_targets ? (
        <span className="flex items-center gap-1 text-emerald-400 font-medium">
          <CheckCircle2 size={11} /> PASS
        </span>
      ) : (
        <span className="flex items-center gap-1 text-amber-400 font-medium">
          <XCircle size={11} /> FAIL
        </span>
      )}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function GatingBenchmarkPanel({ isBackendMode }) {
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
    <div className="border border-gray-800 rounded-xl bg-gray-900/20 p-4 space-y-3" data-testid="gating-benchmark-panel">
      <div className="flex items-center gap-2">
        <FlaskConical size={14} className="text-gray-500" />
        <h3 className="text-sm font-semibold text-gray-400">בנצ׳מרק LLM Gating</h3>
      </div>

      <p className="text-xs text-amber-600/80">
        כלי QA מקומי — מוחק ומייבא מחדש כתבות RSS. דורש ALLOW_DEV_RESET=true ו־CLASSIFICATION_PROVIDER=ollama.
      </p>

      <button
        onClick={handleRun}
        disabled={isRunning}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-700 text-xs text-gray-400 hover:border-gray-600 hover:text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        data-testid="benchmark-run-button"
      >
        <FlaskConical size={12} />
        {isRunning ? "מריץ בנצ׳מרק... (עלול לקחת 15–20 דקות)" : "הרץ בנצ׳מרק מלא"}
      </button>

      {isRunning && (
        <p className="text-xs text-gray-600" data-testid="benchmark-loading">
          שלב 1: baseline — מריץ ייבוא ללא gating (כל כתבה קוראת ל־LLM).<br />
          שלב 2: gated — מריץ ייבוא עם gating פעיל.<br />
          הסבלנות תוגמל בנתונים.
        </p>
      )}

      {error && (
        <div className="flex items-start gap-2 text-xs text-red-400 bg-red-900/10 border border-red-800/30 rounded-lg px-3 py-2" data-testid="benchmark-error">
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div className="space-y-4 text-xs" data-testid="benchmark-result">
          <div className="text-gray-600 text-[10px]">
            provider: <span className="text-gray-400">{result.provider}</span>
          </div>

          {/* Baseline section */}
          <div>
            <div className="font-semibold text-gray-400 border-b border-gray-800 pb-1 mb-2">
              Baseline — gating disabled:
            </div>
            {sources.map(src => (
              <SourceBaselineBlock
                key={src}
                sourceId={src}
                stats={result.baseline?.sources?.[src]}
              />
            ))}
          </div>

          {/* Gated section */}
          <div>
            <div className="font-semibold text-gray-400 border-b border-gray-800 pb-1 mb-2">
              Gating enabled:
            </div>
            {sources.map(src => (
              <SourceGatedBlock
                key={src}
                sourceId={src}
                stats={result.gated?.sources?.[src]}
              />
            ))}
          </div>

          {/* Comparison section */}
          <div>
            <div className="font-semibold text-gray-400 border-b border-gray-800 pb-1 mb-2">
              השוואה:
            </div>
            <div className="space-y-2">
              {sources.map(src =>
                result.comparison?.[src] ? (
                  <ComparisonRow key={src} sourceId={src} comp={result.comparison[src]} />
                ) : null
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
