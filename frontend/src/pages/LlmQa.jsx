/**
 * LLM QA Page — temporary, local-only, not a product page.
 * Route: /llm-qa
 * Only meaningful in backend mode with CLASSIFICATION_PROVIDER=ollama.
 */
import React, { useState, useEffect, useCallback } from "react";
import { useApp } from "@/context/AppContext";
import { FlaskConical, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import DecisionBadge from "@/components/feed/DecisionBadge";
import ClassifiedByBadge from "@/components/debug/ClassifiedByBadge";
import ReasoningTrace from "@/components/debug/ReasoningTrace";
import SectionCard from "@/components/shared/SectionCard";
import StatCard from "@/components/shared/StatCard";
import PageHeader from "@/components/shared/PageHeader";
import EmptyState from "@/components/shared/EmptyState";
import { consoleButton } from "@/components/ops/consoleStyles";
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

// ── Sub-components ─────────────────────────────────────────────────────────────

function MetaCell({ label, value }) {
  return (
    <div className="bg-surface-2 rounded-lg p-1.5">
      <div className="text-text-dim text-[10px]">{label}</div>
      <div className="text-text-secondary truncate" title={value}>{value}</div>
    </div>
  );
}

function QaRow({ item }) {
  const [expanded, setExpanded] = useState(false);
  const decision = item.score?.decision ?? "hidden";
  const isFp = isPossibleFootballFalsePositive(item);

  const cells = [
    { label: "sport", value: item.sport ?? "—" },
    { label: "league", value: item.league ?? "—" },
    { label: "event_type", value: item.eventType ?? "—" },
    { label: "importance", value: item.importance ?? "—" },
    { label: "confidence", value: item.confidence != null ? `${Math.round(item.confidence * 100)}%` : "—" },
    { label: "source", value: item.source },
    { label: "entities", value: (item.entities ?? []).join(", ") || "—" },
    { label: "matched_topic", value: item.score?.matchedTopic ?? "—" },
  ];

  return (
    <div className={cn(
      "border rounded-xl overflow-hidden transition-colors",
      isFp ? "border-signal-push/30 bg-signal-push/5"
      : decision === "hidden" ? "border-signal-hidden/25 bg-signal-hidden/5"
      : decision === "push" ? "border-signal-push/25 bg-signal-push/5"
      : "border-border bg-surface-1"
    )}>
      <button
        className="w-full text-start p-3 flex items-start justify-between gap-3 hover:bg-surface-2/50 transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <DecisionBadge decision={decision} size="xs" />
            <ClassifiedByBadge value={item.classifiedBy ?? "rules"} />
            {isFp && (
              <span className="text-[10px] bg-signal-push/12 text-signal-push border border-signal-push/30 rounded-full px-1.5 py-0.5">
                Football FP?
              </span>
            )}
          </div>
          <p className="text-sm text-foreground font-medium leading-snug line-clamp-2">{item.title}</p>
          <p className="text-xs text-text-dim mt-0.5">
            {item.source} · {item.sport} · {item.league ?? "—"}
          </p>
        </div>
        <span className="text-text-dim text-xs flex-shrink-0 mt-0.5">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="border-t border-border/60 p-3 space-y-2 text-xs">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {cells.map(({ label, value }) => (
              <MetaCell key={label} label={label} value={value} />
            ))}
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <ClassifiedByBadge value={item.classifiedBy ?? "rules"} />
            {item.classificationProvider && item.classificationProvider !== "rules" && (
              <span className="text-[10px] text-text-secondary bg-surface-2 border border-border rounded-full px-1.5 py-0.5 font-mono">
                {item.classificationProvider}
              </span>
            )}
            {item.classificationConfidence != null && (
              <span className="text-[10px] text-text-dim">
                LLM confidence: {Math.round(item.classificationConfidence * 100)}%
              </span>
            )}
          </div>
          {item.classificationReason && (
            <p className="text-[11px] text-text-dim italic">{item.classificationReason}</p>
          )}

          {(item.score?.reasoning ?? []).length > 0 && <ReasoningTrace reasoning={item.score.reasoning} />}
        </div>
      )}
    </div>
  );
}

function ProviderStatusSection({ status, error }) {
  if (error) {
    return (
      <SectionCard title="ספק סיווג — שגיאה">
        <p className="text-xs text-signal-hidden">{error}</p>
      </SectionCard>
    );
  }
  if (!status) {
    return (
      <SectionCard title="ספק סיווג">
        <p className="text-xs text-text-dim">טוען סטטוס ספק...</p>
      </SectionCard>
    );
  }

  const providerColor =
    status.provider === "disabled" ? "text-text-dim"
    : status.can_classify ? "text-signal-high"
    : "text-signal-push";

  return (
    <SectionCard title="ספק סיווג">
      <div className="space-y-3">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          <div className="bg-surface-2 rounded-lg p-2">
            <div className="text-text-dim text-[10px] mb-0.5">CLASSIFICATION_PROVIDER</div>
            <div className={cn("font-mono font-medium", providerColor)}>{status.provider}</div>
          </div>
          <div className="bg-surface-2 rounded-lg p-2">
            <div className="text-text-dim text-[10px] mb-0.5">can_classify</div>
            <div className={status.can_classify ? "text-signal-high font-medium" : "text-signal-hidden font-medium"}>
              {status.can_classify ? "true" : "false"}
            </div>
          </div>
          <div className="bg-surface-2 rounded-lg p-2">
            <div className="text-text-dim text-[10px] mb-0.5">CLASSIFICATION_MODEL</div>
            <div className="text-text-secondary font-mono">{status.model ?? "—"}</div>
          </div>
          <div className="bg-surface-2 rounded-lg p-2">
            <div className="text-text-dim text-[10px] mb-0.5">ALLOW_DEV_RESET</div>
            <div className={status.reset_allowed ? "text-signal-push font-medium" : "text-text-dim"}>
              {status.reset_allowed ? "true" : "false"}
            </div>
          </div>
        </div>
        {status.base_url && (
          <div className="bg-surface-2 rounded-lg p-2 text-xs">
            <span className="text-text-dim">CLASSIFICATION_OLLAMA_BASE_URL: </span>
            <span className="text-text-secondary font-mono">{status.base_url}</span>
          </div>
        )}
        {!status.can_classify && (
          <div className="bg-signal-push/10 border border-signal-push/25 rounded-lg px-3 py-2 text-xs text-signal-push">
            הספק לא פעיל — סיווג LLM מושבת. הגדר{" "}
            <span className="font-mono">CLASSIFICATION_PROVIDER=ollama</span>{" "}
            ב-<span className="font-mono">backend/.env</span>.
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function ResetSection({
  resetAllowed, showConfirm, setShowConfirm,
  confirmText, setConfirmText,
  resetting, lastResult, error, onReset,
}) {
  return (
    <SectionCard
      title="איפוס נתוני RSS"
      actions={
        !showConfirm && (
          <button
            onClick={() => setShowConfirm(true)}
            disabled={!resetAllowed || resetting}
            className={consoleButton("danger", "px-3 py-1.5 text-xs")}
          >
            איפוס...
          </button>
        )
      }
    >
      <div className="space-y-3">
        <p className="text-xs text-text-dim">
          מוחק כל כתבות rss_ וריצות ייבוא. נתוני seed ופרופילים לא נמחקים.
        </p>

        {!resetAllowed && (
          <div className="text-xs text-text-dim bg-surface-2 rounded-lg p-2">
            מושבת. הגדר <span className="font-mono text-text-secondary">ALLOW_DEV_RESET=true</span>{" "}
            ב-<span className="font-mono text-text-secondary">backend/.env</span> ואתחל את השרת.
          </div>
        )}

        {showConfirm && (
          <div className="bg-signal-hidden/8 border border-signal-hidden/25 rounded-lg p-3 space-y-2">
            <p className="text-xs text-signal-hidden font-medium">
              פעולה בלתי הפיכה. הקלד <span className="font-mono bg-signal-hidden/15 px-1 rounded">RESET</span> לאישור:
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder="הקלד RESET"
                className="flex-1 bg-surface-2 border border-signal-hidden/40 rounded-lg px-3 py-1.5 text-xs font-mono text-signal-hidden placeholder-text-dim focus:outline-none focus:border-signal-hidden/60"
                dir="ltr"
              />
              <button
                onClick={onReset}
                disabled={confirmText !== "RESET" || resetting}
                className={consoleButton("danger", "px-3 py-1.5 text-xs")}
              >
                {resetting ? "מאפס..." : "אפס"}
              </button>
              <button
                onClick={() => { setShowConfirm(false); setConfirmText(""); }}
                className={consoleButton("ghost")}
              >
                ביטול
              </button>
            </div>
          </div>
        )}

        {error && <p className="text-xs text-signal-hidden">{error}</p>}

        {lastResult && (
          <div className="text-xs text-text-secondary bg-surface-2 rounded-lg p-2 font-mono">
            ✓ נמחקו {lastResult.deleted_articles} כתבות ו-{lastResult.deleted_ingestion_runs} ריצות
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function IngestionSection({ ingesting, ingestResults, onIngest }) {
  const sources = [
    { id: "walla_sport", label: "וואלה ספורט" },
    { id: "israel_hayom_sport", label: "ישראל היום" },
    { id: "ynet_sport", label: "ynet ספורט" },
  ];

  return (
    <SectionCard title="ייבוא כתבות">
      <div className="space-y-3">
        <div className="flex gap-2 flex-wrap">
          {sources.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => onIngest(id)}
              disabled={ingesting != null}
              className={consoleButton("ghost")}
            >
              {ingesting === id ? "מייבא..." : `ייבא ${label}`}
            </button>
          ))}
          <button
            onClick={() => onIngest(null)}
            disabled={ingesting != null}
            className={consoleButton("primary", "px-3 py-1.5 text-xs")}
          >
            {ingesting === "both" ? "מייבא..." : "ייבא הכל"}
          </button>
        </div>

        {ingestResults.length > 0 && (
          <div className="space-y-1">
            {ingestResults.map((r) => (
              <div key={r.source_id} className="text-[11px] text-text-secondary bg-surface-2 rounded-lg px-2 py-1 font-mono">
                {r.source_id}: fetched={r.fetched} inserted={r.inserted} filtered={r.skipped_filtered ?? 0} dup={r.skipped_duplicate ?? 0} failed={r.failed ?? 0}
              </div>
            ))}
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function BackfillSection({
  backfilling, backfillForce, setBackfillForce,
  backfillDryRun, setBackfillDryRun,
  backfillResult, backfillError, onBackfill,
}) {
  return (
    <SectionCard title="Backfill סיווג LLM">
      <div className="space-y-3">
        <p className="text-xs text-text-dim">
          מסווג מחדש כתבות קיימות ממקורות עברית רחבים עם ה-LLM.
        </p>

        <div className="flex items-center gap-4">
          <label className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={backfillForce}
              onChange={(e) => setBackfillForce(e.target.checked)}
              className="rounded border-border bg-surface-2 text-signal-feed"
            />
            force (כולל כבר מסווגי LLM)
          </label>
          <label className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={backfillDryRun}
              onChange={(e) => setBackfillDryRun(e.target.checked)}
              className="rounded border-border bg-surface-2 text-signal-push"
            />
            dry_run (ללא כתיבה ל-DB)
          </label>
        </div>

        <div className="flex gap-2 flex-wrap">
          {HEBREW_BROAD_SOURCES.map((sourceId) => (
            <button
              key={sourceId}
              onClick={() => onBackfill(sourceId)}
              disabled={backfilling}
              className={consoleButton("ghost")}
            >
              {backfilling ? "מבצע..." : `Backfill ${sourceId}`}
            </button>
          ))}
        </div>

        {backfillError && <p className="text-xs text-signal-hidden">{backfillError}</p>}

        {backfillResult && (
          <div className="text-[11px] text-text-secondary bg-surface-2 rounded-lg px-3 py-2 font-mono space-y-0.5">
            <div>provider: {backfillResult.provider}</div>
            <div>processed: {backfillResult.processed}</div>
            <div>llm_classified: {backfillResult.llm_classified}</div>
            <div>guardrail_corrections: {backfillResult.guardrail_corrections}</div>
            <div>fallback_count: {backfillResult.fallback_count}</div>
            <div>low_confidence_count: {backfillResult.low_confidence_count}</div>
            <div>skipped_already_classified: {backfillResult.skipped_already_classified}</div>
            {backfillResult.dry_run && <div className="text-signal-push">dry_run=true — לא נכתב</div>}
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function MetricsSection({ metrics, timeFilter, setTimeFilter, feedError }) {
  if (feedError) {
    return (
      <SectionCard title="מדדים">
        <p className="text-xs text-signal-hidden">שגיאה בטעינת הפיד: {feedError}</p>
      </SectionCard>
    );
  }

  const { total, wallaCount, ihCount, ynetCount, visibleForGuy, hiddenForGuy, unknownCount,
          classifiedByBreakdown, sportBreakdown, decisionBreakdown, usedFallback } = metrics;

  return (
    <SectionCard
      title="מדדים"
      actions={
        <div className="flex gap-1">
          {["24h", "all"].map((f) => (
            <button
              key={f}
              onClick={() => setTimeFilter(f)}
              className={cn(
                "text-xs px-2.5 py-1 rounded-full border transition-colors",
                timeFilter === f
                  ? "bg-surface-3 border-text-dim text-foreground"
                  : "bg-surface-1 border-border text-text-dim hover:border-text-dim"
              )}
            >
              {f === "24h" ? "24 שעות" : "הכל"}
            </button>
          ))}
        </div>
      }
    >
      <div className="space-y-4">
        <p className="text-text-dim text-xs">מקורות עברית בלבד: וואלה + ישראל היום + ynet</p>

        {usedFallback && (
          <div className="bg-signal-push/10 border border-signal-push/25 rounded-lg px-3 py-1.5 text-xs text-signal-push">
            אין כתבות מ-24 השעות האחרונות — מוצג all-time כ-fallback
          </div>
        )}

        <div className="grid grid-cols-3 md:grid-cols-7 gap-2">
          <StatCard label="סה״כ" value={total} className="px-2 py-2 text-center" />
          <StatCard label="וואלה" value={wallaCount} tone="feed" className="px-2 py-2 text-center" />
          <StatCard label="ישראל היום" value={ihCount} tone="ai" className="px-2 py-2 text-center" />
          <StatCard label="ynet" value={ynetCount} tone="feed" className="px-2 py-2 text-center" />
          <StatCard label="ניראה לגיא" value={visibleForGuy} tone="high" className="px-2 py-2 text-center" />
          <StatCard label="מוסתר לגיא" value={hiddenForGuy} tone="hidden" className="px-2 py-2 text-center" />
          <StatCard label="sport=unknown" value={unknownCount} tone="push" className="px-2 py-2 text-center" />
        </div>

        <div className="grid md:grid-cols-3 gap-3">
          {[
            { title: "classified_by", data: classifiedByBreakdown },
            { title: "sport", data: sportBreakdown },
            { title: "decision (Guy)", data: decisionBreakdown },
          ].map(({ title, data }) => (
            <div key={title} className="bg-surface-2 border border-border rounded-[10px] p-3">
              <p className="text-[10px] text-text-dim uppercase tracking-wide mb-2">{title}</p>
              <div className="space-y-1">
                {Object.entries(data).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between gap-2">
                    <span className="text-xs text-text-secondary font-mono truncate">{k}</span>
                    <span className="text-xs text-foreground font-medium flex-shrink-0">{v}</span>
                  </div>
                ))}
                {Object.keys(data).length === 0 && <p className="text-xs text-text-dim">—</p>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </SectionCard>
  );
}

// ── Tab panel ─────────────────────────────────────────────────────────────────

const TABS = [
  { id: "llm",         label: "LLM",         active: "text-signal-feed border-signal-feed" },
  { id: "guardrail",   label: "Guardrail",   active: "text-signal-ai border-signal-ai" },
  { id: "fallback",    label: "Fallback",    active: "text-signal-hidden border-signal-hidden" },
  { id: "unknown",     label: "Unknown",     active: "text-text-secondary border-text-secondary" },
  { id: "visible",     label: "ניראה",       active: "text-signal-high border-signal-high" },
  { id: "football_fp", label: "Football FP?", active: "text-signal-push border-signal-push" },
  { id: "push",        label: "Push",        active: "text-signal-push border-signal-push" },
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
    llm:         metrics.items.filter((a) => a.classifiedBy === "llm"),
    guardrail:   metrics.items.filter((a) => a.classifiedBy === "llm+rules_guardrail"),
    fallback:    metrics.items.filter((a) => a.classifiedBy?.startsWith("rules_fallback_")),
    unknown:     metrics.items.filter((a) => a.sport === "unknown"),
    visible:     metrics.items.filter((a) => a.score?.decision !== "hidden"),
    football_fp: metrics.items.filter(isPossibleFootballFalsePositive),
    push:        metrics.items.filter((a) => a.score?.decision === "push"),
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
        setIngestResults((prev) => [
          ...prev.filter((x) => x.source_id !== r.source_id),
          r,
        ]);
      } else {
        const results = [];
        for (const sourceId of HEBREW_BROAD_SOURCES) {
          results.push(await runIngestion(sourceId));
        }
        setIngestResults((prev) => {
          const filtered = prev.filter(
            (x) => !HEBREW_BROAD_SOURCES.includes(x.source_id)
          );
          return [...filtered, ...results];
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
      <EmptyState
        icon={FlaskConical}
        title="עמוד זה זמין במצב שרת בלבד"
        hint="הפעל את השרת האחורי והגדר VITE_DATA_MODE=backend."
      />
    );
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  const copyClass =
    copyStatus === "ok" ? "bg-signal-high/10 border-signal-high/30 text-signal-high"
    : copyStatus === "err" ? "bg-signal-hidden/10 border-signal-hidden/30 text-signal-hidden"
    : "bg-surface-2 border-border text-text-secondary hover:text-foreground hover:border-text-dim";

  return (
    <div className="max-w-4xl space-y-5">
      <PageHeader
        title="בדיקת סיווג LLM"
        icon={FlaskConical}
        subtitle="עמוד QA — לא עמוד מוצרי"
      >
        {loading && <span className="text-xs text-text-dim animate-pulse">טוען...</span>}
        <button onClick={loadData} disabled={loading} className={consoleButton("ghost")}>
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> רענן
        </button>
        <button onClick={handleCopySummary} className={cn("text-xs rounded-lg px-3 py-1.5 border transition-colors", copyClass)}>
          {copyStatus === "ok" ? "✓ הועתק" : copyStatus === "err" ? "✗ שגיאה" : "העתק QA Summary"}
        </button>
      </PageHeader>

      <div className="bg-signal-push/8 border border-signal-push/25 rounded-lg px-3 py-2">
        <p className="text-xs text-signal-push">
          QA בלבד · עמוד זה לא מופיע בניווט הרגיל ·{" "}
          <span className="font-mono">ALLOW_DEV_RESET=true</span>{" "}
          נדרש לאיפוס · אל תריץ Eurohoops/Sportando מכאן
        </p>
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

      <IngestionSection ingesting={ingesting} ingestResults={ingestResults} onIngest={handleIngest} />

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

      <MetricsSection metrics={metrics} timeFilter={timeFilter} setTimeFilter={setTimeFilter} feedError={feedError} />

      {/* Tab panel */}
      <div className="space-y-3">
        <div className="flex gap-0.5 border-b border-border overflow-x-auto">
          {TABS.map((tab) => {
            const count = tabBuckets[tab.id]?.length ?? 0;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "px-3 py-2.5 text-xs font-medium border-b-2 whitespace-nowrap transition-colors",
                  activeTab === tab.id ? tab.active : "text-text-dim border-transparent hover:text-text-secondary"
                )}
              >
                {tab.label} <span className="text-text-dim">({count})</span>
              </button>
            );
          })}
        </div>

        <div className="space-y-2">
          {(tabBuckets[activeTab] ?? []).length === 0 ? (
            <EmptyState icon={FlaskConical} title="אין כתבות בקטגוריה זו" />
          ) : (
            (tabBuckets[activeTab] ?? []).map((item) => <QaRow key={item.id} item={item} />)
          )}
        </div>
      </div>
    </div>
  );
}
