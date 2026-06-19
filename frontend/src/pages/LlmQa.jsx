/**
 * LLM QA Page — temporary, local-only, not a product page.
 * Route: /llm-qa
 * Only meaningful in backend mode with CLASSIFICATION_PROVIDER=ollama.
 */
import React, { useState, useEffect, useCallback } from "react";
import { useApp } from "@/context/AppContext";
import DecisionBadge from "@/components/feed/DecisionBadge";
import {
  getClassifyStatus,
  getDebugFeed,
  runIngestion,
  classifyBackfill,
  resetRssData,
} from "@/api/client";
import { normalizeScoredArticleFromApi } from "@/api/normalizers";
import {
  calcMetrics,
  buildQaSummary,
  isPossibleFootballFalsePositive,
  HEBREW_BROAD_SOURCES,
} from "./llmQaHelpers";

// ── Visual constants ───────────────────────────────────────────────────────────

const CLASSIFIED_BY_STYLES = {
  rules:                            "bg-gray-800/80 text-gray-400 border-gray-700/40",
  llm:                              "bg-blue-950/60 text-blue-300 border-blue-700/40",
  "llm+rules_guardrail":            "bg-yellow-950/60 text-yellow-300 border-yellow-700/40",
  rules_fallback_after_llm_failure: "bg-red-950/60 text-red-300 border-red-700/40",
  rules_fallback_low_confidence:    "bg-orange-950/60 text-orange-300 border-orange-700/40",
};

// ── Sub-components ─────────────────────────────────────────────────────────────

function ClassifiedByBadge({ value }) {
  const style = CLASSIFIED_BY_STYLES[value] ?? CLASSIFIED_BY_STYLES.rules;
  return (
    <span className={`text-[10px] border rounded px-1.5 py-0.5 font-mono ${style}`}>
      {value}
    </span>
  );
}

function Stat({ label, value, color = "text-gray-300" }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-3 text-center">
      <div className={`text-xl font-bold ${color}`}>{value}</div>
      <div className="text-[10px] text-gray-600 mt-0.5 leading-tight">{label}</div>
    </div>
  );
}

function QaRow({ item }) {
  const [expanded, setExpanded] = useState(false);
  const decision = item.score?.decision ?? "hidden";
  const isFp = isPossibleFootballFalsePositive(item);

  return (
    <div className={`border rounded-lg overflow-hidden transition-all ${
      isFp ? "border-orange-700/40 bg-orange-950/10"
      : decision === "hidden" ? "border-red-900/30 bg-red-950/10"
      : decision === "push" ? "border-amber-700/40 bg-amber-950/10"
      : "border-gray-800 bg-gray-900/50"
    }`}>
      <button
        className="w-full text-right p-3 flex items-start justify-between gap-3 hover:bg-white/2 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <DecisionBadge decision={decision} size="xs" />
            <ClassifiedByBadge value={item.classifiedBy ?? "rules"} />
            {isFp && (
              <span className="text-[10px] bg-orange-950/60 text-orange-300 border border-orange-700/40 rounded px-1.5 py-0.5">
                Football FP?
              </span>
            )}
          </div>
          <p className="text-sm text-gray-200 font-medium leading-snug line-clamp-2 text-right">
            {item.title}
          </p>
          <p className="text-xs text-gray-600 mt-0.5">
            {item.source} · {item.sport} · {item.league ?? "—"}
          </p>
        </div>
        <span className="text-gray-700 text-xs flex-shrink-0 mt-0.5">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="border-t border-gray-800/60 p-3 space-y-2 text-xs">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {[
              { label: "sport", value: item.sport ?? "—" },
              { label: "league", value: item.league ?? "—" },
              { label: "event_type", value: item.eventType ?? "—" },
              { label: "importance", value: item.importance ?? "—" },
              { label: "confidence", value: item.confidence != null ? `${Math.round(item.confidence * 100)}%` : "—" },
              { label: "source", value: item.source },
              { label: "entities", value: (item.entities ?? []).join(", ") || "—" },
              { label: "matched_topic", value: item.score?.matchedTopic ?? "—" },
            ].map(({ label, value }) => (
              <div key={label} className="bg-gray-800/50 rounded p-1.5">
                <div className="text-gray-600 text-[10px]">{label}</div>
                <div className="text-gray-300 truncate" title={value}>{value}</div>
              </div>
            ))}
          </div>

          {/* LLM fields */}
          <div className="flex items-center gap-2 flex-wrap">
            <ClassifiedByBadge value={item.classifiedBy ?? "rules"} />
            {item.classificationProvider && item.classificationProvider !== "rules" && (
              <span className="text-[10px] text-gray-500 bg-gray-800/60 border border-gray-700/40 rounded px-1.5 py-0.5 font-mono">
                {item.classificationProvider}
              </span>
            )}
            {item.classificationConfidence != null && (
              <span className="text-[10px] text-gray-500">
                LLM confidence: {Math.round(item.classificationConfidence * 100)}%
              </span>
            )}
          </div>
          {item.classificationReason && (
            <p className="text-[11px] text-gray-500 italic">{item.classificationReason}</p>
          )}

          {/* Reasoning chain */}
          {(item.score?.reasoning ?? []).length > 0 && (
            <div className="space-y-0.5">
              {item.score.reasoning.map((line, i) => {
                const isFinal = line.includes("החלטה סופית");
                return (
                  <p key={i} className={`leading-relaxed ${isFinal ? "text-gray-200 font-medium" : "text-gray-500"}`}>
                    {i + 1}. {line}
                  </p>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ProviderStatusSection({ status, error }) {
  if (error) {
    return (
      <section className="border border-red-900/40 bg-red-950/10 rounded-lg p-4">
        <h2 className="text-sm font-semibold text-red-400 mb-1">ספק סיווג — שגיאה</h2>
        <p className="text-xs text-red-500">{error}</p>
      </section>
    );
  }
  if (!status) {
    return (
      <section className="border border-gray-800 rounded-lg p-4">
        <p className="text-xs text-gray-600">טוען סטטוס ספק...</p>
      </section>
    );
  }

  const providerColor =
    status.provider === "disabled" ? "text-gray-500"
    : status.can_classify ? "text-emerald-400"
    : "text-orange-400";

  return (
    <section className="border border-gray-800 rounded-lg p-4 space-y-3">
      <h2 className="text-sm font-semibold text-gray-300">ספק סיווג</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        <div className="bg-gray-800/50 rounded p-2">
          <div className="text-gray-600 text-[10px] mb-0.5">CLASSIFICATION_PROVIDER</div>
          <div className={`font-mono font-medium ${providerColor}`}>{status.provider}</div>
        </div>
        <div className="bg-gray-800/50 rounded p-2">
          <div className="text-gray-600 text-[10px] mb-0.5">can_classify</div>
          <div className={status.can_classify ? "text-emerald-400 font-medium" : "text-red-400 font-medium"}>
            {status.can_classify ? "true" : "false"}
          </div>
        </div>
        <div className="bg-gray-800/50 rounded p-2">
          <div className="text-gray-600 text-[10px] mb-0.5">CLASSIFICATION_MODEL</div>
          <div className="text-gray-300 font-mono">{status.model ?? "—"}</div>
        </div>
        <div className="bg-gray-800/50 rounded p-2">
          <div className="text-gray-600 text-[10px] mb-0.5">ALLOW_DEV_RESET</div>
          <div className={status.reset_allowed ? "text-yellow-400 font-medium" : "text-gray-500"}>
            {status.reset_allowed ? "true" : "false"}
          </div>
        </div>
      </div>
      {status.base_url && (
        <div className="bg-gray-800/30 rounded p-2 text-xs">
          <span className="text-gray-600">CLASSIFICATION_OLLAMA_BASE_URL: </span>
          <span className="text-gray-400 font-mono">{status.base_url}</span>
        </div>
      )}
      {!status.can_classify && (
        <div className="bg-yellow-950/30 border border-yellow-900/40 rounded px-3 py-2 text-xs text-yellow-600">
          הספק לא פעיל — סיווג LLM מושבת. הגדר{" "}
          <span className="font-mono text-yellow-500">CLASSIFICATION_PROVIDER=ollama</span>{" "}
          ב-<span className="font-mono text-yellow-500">backend/.env</span>.
        </div>
      )}
    </section>
  );
}

function ResetSection({
  resetAllowed, showConfirm, setShowConfirm,
  confirmText, setConfirmText,
  resetting, lastResult, error, onReset,
}) {
  return (
    <section className="border border-gray-800 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-300">איפוס נתוני RSS</h2>
          <p className="text-xs text-gray-600 mt-0.5">
            מוחק כל כתבות rss_ וריצות ייבוא. נתוני seed ופרופילים לא נמחקים.
          </p>
        </div>
        {!showConfirm && (
          <button
            onClick={() => setShowConfirm(true)}
            disabled={!resetAllowed || resetting}
            className={`text-xs px-3 py-1.5 rounded border transition-colors flex-shrink-0 ${
              resetAllowed
                ? "bg-red-950/40 border-red-800/60 text-red-400 hover:border-red-700 hover:text-red-300"
                : "bg-gray-800/40 border-gray-700/40 text-gray-600 cursor-not-allowed"
            }`}
          >
            איפוס...
          </button>
        )}
      </div>

      {!resetAllowed && (
        <div className="text-xs text-gray-600 bg-gray-800/30 rounded p-2">
          מושבת. הגדר{" "}
          <span className="font-mono text-gray-400">ALLOW_DEV_RESET=true</span>{" "}
          ב-<span className="font-mono text-gray-400">backend/.env</span> ואתחל את השרת.
        </div>
      )}

      {showConfirm && (
        <div className="bg-red-950/20 border border-red-900/40 rounded p-3 space-y-2">
          <p className="text-xs text-red-400 font-medium">
            פעולה בלתי הפיכה. הקלד <span className="font-mono bg-red-950/60 px-1 rounded">RESET</span> לאישור:
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              value={confirmText}
              onChange={e => setConfirmText(e.target.value)}
              placeholder="הקלד RESET"
              className="flex-1 bg-gray-900 border border-red-800/50 rounded px-3 py-1.5 text-xs font-mono text-red-300 placeholder-gray-700 focus:outline-none focus:border-red-700"
              dir="ltr"
            />
            <button
              onClick={onReset}
              disabled={confirmText !== "RESET" || resetting}
              className="text-xs px-3 py-1.5 rounded border bg-red-900/50 border-red-700 text-red-300 hover:bg-red-900/70 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {resetting ? "מאפס..." : "אפס"}
            </button>
            <button
              onClick={() => { setShowConfirm(false); setConfirmText(""); }}
              className="text-xs px-3 py-1.5 rounded border border-gray-700 text-gray-500 hover:text-gray-300 transition-colors"
            >
              ביטול
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="text-xs text-red-400">{error}</p>
      )}

      {lastResult && (
        <div className="text-xs text-gray-500 bg-gray-800/30 rounded p-2 font-mono">
          ✓ נמחקו {lastResult.deleted_articles} כתבות ו-{lastResult.deleted_ingestion_runs} ריצות
        </div>
      )}
    </section>
  );
}

function IngestionSection({ ingesting, ingestResults, onIngest }) {
  const sources = [
    { id: "walla_sport", label: "וואלה ספורט" },
    { id: "israel_hayom_sport", label: "ישראל היום" },
  ];

  return (
    <section className="border border-gray-800 rounded-lg p-4 space-y-3">
      <h2 className="text-sm font-semibold text-gray-300">ייבוא כתבות</h2>
      <div className="flex gap-2 flex-wrap">
        {sources.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => onIngest(id)}
            disabled={ingesting != null}
            className="text-xs px-3 py-1.5 rounded border border-blue-800/60 bg-blue-950/30 text-blue-400 hover:border-blue-700 hover:text-blue-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {ingesting === id ? "מייבא..." : `ייבא ${label}`}
          </button>
        ))}
        <button
          onClick={() => onIngest(null)}
          disabled={ingesting != null}
          className="text-xs px-3 py-1.5 rounded border border-emerald-800/60 bg-emerald-950/30 text-emerald-400 hover:border-emerald-700 hover:text-emerald-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {ingesting === "both" ? "מייבא..." : "ייבא הכל (במקביל)"}
        </button>
      </div>

      {ingestResults.length > 0 && (
        <div className="space-y-1">
          {ingestResults.map(r => (
            <div key={r.source_id} className="text-[11px] text-gray-500 bg-gray-800/30 rounded px-2 py-1 font-mono">
              {r.source_id}: fetched={r.fetched} inserted={r.inserted} filtered={r.skipped_filtered ?? 0} dup={r.skipped_duplicate ?? 0} failed={r.failed ?? 0}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function BackfillSection({
  backfilling, backfillForce, setBackfillForce,
  backfillDryRun, setBackfillDryRun,
  backfillResult, backfillError, onBackfill,
}) {
  return (
    <section className="border border-gray-800 rounded-lg p-4 space-y-3">
      <h2 className="text-sm font-semibold text-gray-300">Backfill סיווג LLM</h2>
      <p className="text-xs text-gray-600">
        מסווג מחדש כתבות קיימות ממקורות עברית רחבים עם ה-LLM.
      </p>

      <div className="flex items-center gap-4">
        <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer">
          <input
            type="checkbox"
            checked={backfillForce}
            onChange={e => setBackfillForce(e.target.checked)}
            className="rounded border-gray-600 bg-gray-800 text-blue-500"
          />
          force (כולל כבר מסווגי LLM)
        </label>
        <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer">
          <input
            type="checkbox"
            checked={backfillDryRun}
            onChange={e => setBackfillDryRun(e.target.checked)}
            className="rounded border-gray-600 bg-gray-800 text-yellow-500"
          />
          dry_run (ללא כתיבה ל-DB)
        </label>
      </div>

      <div className="flex gap-2 flex-wrap">
        {["walla_sport", "israel_hayom_sport"].map(sourceId => (
          <button
            key={sourceId}
            onClick={() => onBackfill(sourceId)}
            disabled={backfilling}
            className="text-xs px-3 py-1.5 rounded border border-purple-800/60 bg-purple-950/30 text-purple-400 hover:border-purple-700 hover:text-purple-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {backfilling ? "מבצע..." : `Backfill ${sourceId}`}
          </button>
        ))}
      </div>

      {backfillError && (
        <p className="text-xs text-red-400">{backfillError}</p>
      )}

      {backfillResult && (
        <div className="text-[11px] text-gray-500 bg-gray-800/30 rounded px-3 py-2 font-mono space-y-0.5">
          <div>provider: {backfillResult.provider}</div>
          <div>processed: {backfillResult.processed}</div>
          <div>llm_classified: {backfillResult.llm_classified}</div>
          <div>guardrail_corrections: {backfillResult.guardrail_corrections}</div>
          <div>fallback_count: {backfillResult.fallback_count}</div>
          <div>low_confidence_count: {backfillResult.low_confidence_count}</div>
          <div>skipped_already_classified: {backfillResult.skipped_already_classified}</div>
          {backfillResult.dry_run && <div className="text-yellow-600">dry_run=true — לא נכתב</div>}
        </div>
      )}
    </section>
  );
}

function MetricsSection({ metrics, timeFilter, setTimeFilter, feedError }) {
  if (feedError) {
    return (
      <section className="border border-red-900/40 rounded-lg p-4">
        <p className="text-xs text-red-400">שגיאה בטעינת הפיד: {feedError}</p>
      </section>
    );
  }

  const { total, wallaCount, ihCount, visibleForGuy, hiddenForGuy, unknownCount,
          classifiedByBreakdown, sportBreakdown, decisionBreakdown, usedFallback } = metrics;

  return (
    <section className="border border-gray-800 rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-sm font-semibold text-gray-300">
          מדדים{" "}
          <span className="text-gray-600 font-normal text-xs">(מקורות עברית בלבד: וואלה + ישראל היום)</span>
        </h2>
        <div className="flex gap-1">
          {["24h", "all"].map(f => (
            <button
              key={f}
              onClick={() => setTimeFilter(f)}
              className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                timeFilter === f
                  ? "bg-gray-700 border-gray-500 text-white"
                  : "bg-gray-900 border-gray-800 text-gray-500 hover:border-gray-700"
              }`}
            >
              {f === "24h" ? "24 שעות" : "הכל"}
            </button>
          ))}
        </div>
      </div>

      {usedFallback && (
        <div className="bg-yellow-950/20 border border-yellow-900/30 rounded px-3 py-1.5 text-xs text-yellow-700">
          אין כתבות מ-24 השעות האחרונות — מוצג all-time כ-fallback
        </div>
      )}

      <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
        <Stat label="סה״כ" value={total} />
        <Stat label="וואלה" value={wallaCount} color="text-blue-400" />
        <Stat label="ישראל היום" value={ihCount} color="text-cyan-400" />
        <Stat label="ניראה לגיא" value={visibleForGuy} color="text-emerald-400" />
        <Stat label="מוסתר לגיא" value={hiddenForGuy} color="text-red-400" />
        <Stat label="sport=unknown" value={unknownCount} color="text-yellow-500" />
      </div>

      {/* Breakdowns */}
      <div className="grid md:grid-cols-3 gap-3">
        {[
          { title: "classified_by", data: classifiedByBreakdown },
          { title: "sport", data: sportBreakdown },
          { title: "decision (Guy)", data: decisionBreakdown },
        ].map(({ title, data }) => (
          <div key={title} className="bg-gray-900/50 border border-gray-800 rounded-lg p-3">
            <p className="text-[10px] text-gray-600 uppercase tracking-wide mb-2">{title}</p>
            <div className="space-y-1">
              {Object.entries(data).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-2">
                  <span className="text-xs text-gray-400 font-mono truncate">{k}</span>
                  <span className="text-xs text-gray-300 font-medium flex-shrink-0">{v}</span>
                </div>
              ))}
              {Object.keys(data).length === 0 && (
                <p className="text-xs text-gray-700">—</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ── Tab panel ─────────────────────────────────────────────────────────────────

const TABS = [
  { id: "llm",         label: "LLM",         activeStyle: "text-blue-400 border-blue-400" },
  { id: "guardrail",   label: "Guardrail",    activeStyle: "text-yellow-400 border-yellow-400" },
  { id: "fallback",    label: "Fallback",     activeStyle: "text-red-400 border-red-400" },
  { id: "unknown",     label: "Unknown",      activeStyle: "text-gray-400 border-gray-400" },
  { id: "visible",     label: "ניראה",        activeStyle: "text-emerald-400 border-emerald-400" },
  { id: "football_fp", label: "Football FP?", activeStyle: "text-orange-400 border-orange-400" },
  { id: "push",        label: "Push",         activeStyle: "text-amber-400 border-amber-400" },
];

// ── Main component ─────────────────────────────────────────────────────────────

export default function LlmQa() {
  const { isBackendMode } = useApp();

  const [providerStatus, setProviderStatus] = useState(null);
  const [statusError, setStatusError] = useState(null);
  const [debugItems, setDebugItems] = useState([]);
  const [feedError, setFeedError] = useState(null);
  const [loading, setLoading] = useState(false);

  const [timeFilter, setTimeFilter] = useState("24h");
  const [activeTab, setActiveTab] = useState("llm");

  // Reset
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [resetConfirmText, setResetConfirmText] = useState("");
  const [resetting, setResetting] = useState(false);
  const [lastResetResult, setLastResetResult] = useState(null);
  const [resetError, setResetError] = useState(null);

  // Ingestion
  const [ingesting, setIngesting] = useState(null);
  const [ingestResults, setIngestResults] = useState([]);

  // Backfill
  const [backfillForce, setBackfillForce] = useState(false);
  const [backfillDryRun, setBackfillDryRun] = useState(false);
  const [backfilling, setBackfilling] = useState(false);
  const [backfillResult, setBackfillResult] = useState(null);
  const [backfillError, setBackfillError] = useState(null);

  // Copy
  const [copyStatus, setCopyStatus] = useState(null);

  // ── Data loading ─────────────────────────────────────────────────────────────

  const loadData = useCallback(async () => {
    if (!isBackendMode) return;
    setLoading(true);
    setStatusError(null);
    setFeedError(null);
    try {
      const [statusResult, feedResult] = await Promise.allSettled([
        getClassifyStatus(),
        getDebugFeed("guy"),
      ]);

      if (statusResult.status === "fulfilled") {
        setProviderStatus(statusResult.value);
      } else {
        setStatusError(statusResult.reason?.message ?? "שגיאה בטעינת סטטוס ספק");
      }

      if (feedResult.status === "fulfilled") {
        const raw = feedResult.value;
        const list = Array.isArray(raw) ? raw : (raw.items ?? []);
        setDebugItems(list.map(normalizeScoredArticleFromApi));
      } else {
        setFeedError(feedResult.reason?.message ?? "שגיאה בטעינת הפיד");
      }
    } finally {
      setLoading(false);
    }
  }, [isBackendMode]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Computed ─────────────────────────────────────────────────────────────────

  const metrics = calcMetrics(debugItems, timeFilter);

  const tabBuckets = {
    llm:         metrics.items.filter(a => a.classifiedBy === "llm"),
    guardrail:   metrics.items.filter(a => a.classifiedBy === "llm+rules_guardrail"),
    fallback:    metrics.items.filter(a => a.classifiedBy?.startsWith("rules_fallback_")),
    unknown:     metrics.items.filter(a => a.sport === "unknown"),
    visible:     metrics.items.filter(a => a.score?.decision !== "hidden"),
    football_fp: metrics.items.filter(isPossibleFootballFalsePositive),
    push:        metrics.items.filter(a => a.score?.decision === "push"),
  };

  // ── Handlers ─────────────────────────────────────────────────────────────────

  const handleReset = async () => {
    if (resetConfirmText !== "RESET") return;
    setResetting(true);
    setResetError(null);
    try {
      const result = await resetRssData();
      setLastResetResult(result);
      setShowResetConfirm(false);
      setResetConfirmText("");
      setIngestResults([]);
      await loadData();
    } catch (e) {
      setResetError(e.message);
    } finally {
      setResetting(false);
    }
  };

  const handleIngest = async (sourceId) => {
    setIngesting(sourceId ?? "both");
    try {
      if (sourceId) {
        const r = await runIngestion(sourceId);
        setIngestResults(prev => [
          ...prev.filter(x => x.source_id !== r.source_id),
          r,
        ]);
      } else {
        const [r1, r2] = await Promise.all([
          runIngestion("walla_sport"),
          runIngestion("israel_hayom_sport"),
        ]);
        setIngestResults(prev => {
          const filtered = prev.filter(
            x => !HEBREW_BROAD_SOURCES.includes(x.source_id)
          );
          return [...filtered, r1, r2];
        });
      }
      await loadData();
    } catch {
      // error shown in ingestResults or via loadData feedError
    } finally {
      setIngesting(null);
    }
  };

  const handleBackfill = async (sourceId) => {
    setBackfilling(true);
    setBackfillError(null);
    setBackfillResult(null);
    try {
      const result = await classifyBackfill({
        sourceId,
        dryRun: backfillDryRun,
        force: backfillForce,
      });
      setBackfillResult(result);
      if (!backfillDryRun) await loadData();
    } catch (e) {
      setBackfillError(e.message);
    } finally {
      setBackfilling(false);
    }
  };

  const handleCopySummary = async () => {
    const summary = buildQaSummary({
      timestamp: new Date().toISOString(),
      providerStatus,
      lastResetResult,
      ingestResults,
      metrics,
    });
    try {
      await navigator.clipboard.writeText(summary);
      setCopyStatus("ok");
    } catch {
      setCopyStatus("err");
    }
    setTimeout(() => setCopyStatus(null), 3000);
  };

  // ── Disabled state ────────────────────────────────────────────────────────────

  if (!isBackendMode) {
    return (
      <div className="text-center py-20 space-y-3">
        <p className="text-3xl">🚫</p>
        <p className="text-lg font-semibold text-gray-400">עמוד זה זמין במצב שרת בלבד</p>
        <p className="text-sm text-gray-600">
          הפעל את השרת האחורי והגדר{" "}
          <span className="font-mono text-gray-500">VITE_DATA_MODE=backend</span>
        </p>
      </div>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5 pb-20 md:pb-6">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-start justify-between flex-wrap gap-2">
          <div>
            <h1 className="text-xl font-bold text-white">בדיקת סיווג LLM</h1>
            <p className="text-xs text-gray-500 mt-0.5">עמוד QA זמני ל-PR 11 — לא עמוד מוצרי</p>
          </div>
          <div className="flex items-center gap-2">
            {loading && (
              <span className="text-xs text-gray-600 animate-pulse">טוען...</span>
            )}
            <button
              onClick={loadData}
              disabled={loading}
              className="text-xs bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-gray-400 hover:text-gray-200 hover:border-gray-600 transition-colors disabled:opacity-40"
            >
              רענן
            </button>
            <button
              onClick={handleCopySummary}
              className={`text-xs rounded px-3 py-1.5 border transition-colors ${
                copyStatus === "ok"
                  ? "bg-emerald-900/40 border-emerald-700 text-emerald-400"
                  : copyStatus === "err"
                  ? "bg-red-900/40 border-red-700 text-red-400"
                  : "bg-gray-800 border-gray-700 text-gray-400 hover:text-gray-200 hover:border-gray-600"
              }`}
            >
              {copyStatus === "ok" ? "✓ הועתק" : copyStatus === "err" ? "✗ שגיאה" : "העתק QA Summary"}
            </button>
          </div>
        </div>
        <div className="bg-yellow-950/20 border border-yellow-900/30 rounded px-3 py-2">
          <p className="text-xs text-yellow-700">
            QA בלבד · עמוד זה לא מופיע בניווט הרגיל ·{" "}
            <span className="font-mono text-yellow-600">ALLOW_DEV_RESET=true</span>{" "}
            נדרש לאיפוס · אל תריץ Eurohoops/Sportando מכאן
          </p>
        </div>
      </div>

      <ProviderStatusSection status={providerStatus} error={statusError} />

      <ResetSection
        resetAllowed={providerStatus?.reset_allowed}
        showConfirm={showResetConfirm}
        setShowConfirm={setShowResetConfirm}
        confirmText={resetConfirmText}
        setConfirmText={setResetConfirmText}
        resetting={resetting}
        lastResult={lastResetResult}
        error={resetError}
        onReset={handleReset}
      />

      <IngestionSection
        ingesting={ingesting}
        ingestResults={ingestResults}
        onIngest={handleIngest}
      />

      <BackfillSection
        backfilling={backfilling}
        backfillForce={backfillForce}
        setBackfillForce={setBackfillForce}
        backfillDryRun={backfillDryRun}
        setBackfillDryRun={setBackfillDryRun}
        backfillResult={backfillResult}
        backfillError={backfillError}
        onBackfill={handleBackfill}
      />

      <MetricsSection
        metrics={metrics}
        timeFilter={timeFilter}
        setTimeFilter={setTimeFilter}
        feedError={feedError}
      />

      {/* Tab panel */}
      <div className="space-y-3">
        <div className="flex gap-0.5 border-b border-gray-800 overflow-x-auto">
          {TABS.map(tab => {
            const count = tabBuckets[tab.id]?.length ?? 0;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-3 py-2.5 text-xs font-medium border-b-2 whitespace-nowrap transition-colors ${
                  activeTab === tab.id
                    ? tab.activeStyle
                    : "text-gray-500 border-transparent hover:text-gray-300"
                }`}
              >
                {tab.label}{" "}
                <span className="text-gray-600">({count})</span>
              </button>
            );
          })}
        </div>

        <div className="space-y-2">
          {(tabBuckets[activeTab] ?? []).length === 0 ? (
            <div className="text-center py-10 text-gray-600 text-sm">
              אין כתבות בקטגוריה זו
            </div>
          ) : (
            (tabBuckets[activeTab] ?? []).map(item => (
              <QaRow key={item.id} item={item} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
