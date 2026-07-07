"""
Per-run LLM dependency / classification quality metrics (issue #31).

Pure computation over counters the ingestion pipeline already records —
no new telemetry, no behavior change. The resulting dict is persisted on the
`ingestion_runs` row (JSON column, soft migration) and surfaced through
`GET /api/ingest/quality` and the Sources ops panel.

DENOMINATOR HONESTY (hard rule from Epic #27 / issue #31): these metrics are
computed ONLY inside the normal gated ingestion path (`_run_source`). The
forced classification backfill (`POST /api/classify/backfill`) bypasses the
gate by design and never writes `ingestion_runs` rows, so it can never be
mistaken for production LLM call rate (the 132/134 forced-backfill figure
from the #29 QA is a backfill artifact, not a dependency measurement).

Rates use `None` (not 0) when the denominator is zero — "not measurable this
run" is different from "measured zero". The LLM-disabled path yields
llm_call_rate=0.0 with everything else still measured.
"""
import os
from dataclasses import dataclass, field
from typing import Optional

from app.models.article import Article

# Schema version for the persisted metrics dict — bump on breaking shape change.
METRICS_SCHEMA_VERSION = 1


def _cost_per_call_estimate() -> float:
    """Configurable per-LLM-call cost estimate (e.g. cloud API pricing or an
    amortized local-compute figure). Defaults to 0.0 — local Ollama is free."""
    try:
        return float(os.environ.get("LLM_COST_PER_CALL_ESTIMATE", "0"))
    except ValueError:
        return 0.0


def _rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


@dataclass
class ArticleQualityCounters:
    """Per-article classification-quality accumulation for one source run.

    `observe()` is called once per INSERTED article — skipped duplicates and
    filtered items never reach classification, so they are not part of any
    quality denominator.
    """
    articles: int = 0
    abstained: int = 0                    # sport == "unknown"
    ambiguous: int = 0                    # tagged ambiguous_club
    with_conflicts: int = 0               # ≥1 recorded conflict in the trace
    weighted_evidence_overrides: int = 0  # conflicts with rule=weighted_evidence_override
    events_corrected: int = 0             # event invalidated → news by post-facts validation

    def observe(self, article: Article) -> None:
        self.articles += 1
        if article.sport == "unknown":
            self.abstained += 1
        if "ambiguous_club" in (article.tags or []):
            self.ambiguous += 1
        trace = article.classification_trace or {}
        conflicts = trace.get("conflicts") or []
        if conflicts:
            self.with_conflicts += 1
        self.weighted_evidence_overrides += sum(
            1 for c in conflicts if c.get("rule") == "weighted_evidence_override"
        )
        event_trace = trace.get("event") or {}
        if event_trace.get("corrected") is True:
            self.events_corrected += 1


def compute_run_metrics(
    *,
    counters: ArticleQualityCounters,
    llm_attempts: int,
    llm_successes: int,
    llm_fallback_connect_error: int,
    llm_fallback_timeout_or_parse: int,
    llm_fallback_low_confidence: int,
    llm_skipped: int,
    llm_skip_reasons: dict[str, int],
    llm_call_reasons: dict[str, int],
    llm_avg_ms: Optional[float],
    llm_p95_ms: Optional[float],
    total_ms: float,
) -> dict:
    """Derive the per-run dependency/quality metrics dict.

    new_articles is the universal denominator for call/abstention/ambiguity/
    conflict rates (per the issue: "call rate % of new articles"). Gate-level
    skip rate uses the gate-eligible population (skipped + called) instead —
    articles the gate never saw (provider disabled, non-Hebrew-broad source)
    are not gate decisions.
    """
    new_articles = counters.articles
    fallbacks_total = (
        llm_fallback_connect_error
        + llm_fallback_timeout_or_parse
        + llm_fallback_low_confidence
    )
    gate_eligible = llm_skipped + sum(llm_call_reasons.values())
    cost_per_call = _cost_per_call_estimate()
    cost_per_run = round(llm_attempts * cost_per_call, 6)

    articles_per_minute: Optional[float] = None
    if total_ms > 0 and new_articles > 0:
        articles_per_minute = round(new_articles / (total_ms / 60000.0), 2)

    return {
        "schema_version": METRICS_SCHEMA_VERSION,
        # Counts
        "new_articles": new_articles,
        "llm_attempts": llm_attempts,
        "llm_successes": llm_successes,
        "llm_skipped": llm_skipped,
        "llm_skip_reasons": dict(llm_skip_reasons),
        "llm_call_reasons": dict(llm_call_reasons),
        "fallbacks_total": fallbacks_total,
        "fallback_connect_error": llm_fallback_connect_error,
        "fallback_timeout_or_parse": llm_fallback_timeout_or_parse,
        "fallback_low_confidence": llm_fallback_low_confidence,
        "abstained": counters.abstained,
        "ambiguous": counters.ambiguous,
        "with_conflicts": counters.with_conflicts,
        "weighted_evidence_overrides": counters.weighted_evidence_overrides,
        "events_corrected": counters.events_corrected,
        # Rates (None = denominator was zero, not measurable this run)
        "deterministic_accept_rate": _rate(new_articles - llm_attempts, new_articles),
        "llm_call_rate": _rate(llm_attempts, new_articles),
        "gate_skip_rate": _rate(llm_skipped, gate_eligible),
        "fallback_rate": _rate(fallbacks_total, llm_attempts),
        "low_confidence_fallback_rate": _rate(llm_fallback_low_confidence, llm_attempts),
        "abstention_rate": _rate(counters.abstained, new_articles),
        "ambiguity_rate": _rate(counters.ambiguous, new_articles),
        "conflict_rate": _rate(counters.with_conflicts, new_articles),
        "weighted_evidence_override_rate": _rate(
            counters.weighted_evidence_overrides, new_articles
        ),
        "event_correction_rate": _rate(counters.events_corrected, new_articles),
        # Latency / throughput
        "llm_avg_ms": llm_avg_ms,
        "llm_p95_ms": llm_p95_ms,
        "total_ms": round(total_ms, 1),
        "articles_per_minute": articles_per_minute,
        # Cost estimates (LLM_COST_PER_CALL_ESTIMATE env; 0.0 for local Ollama)
        "cost_per_call_estimate": cost_per_call,
        "estimated_cost_per_run": cost_per_run,
        "estimated_cost_per_1000_articles": (
            round((cost_per_run / new_articles) * 1000, 4) if new_articles > 0 else None
        ),
    }
