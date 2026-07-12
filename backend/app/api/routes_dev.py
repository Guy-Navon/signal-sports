"""
Development-only endpoints. All routes are guarded by ALLOW_DEV_RESET=true.
Set ALLOW_DEV_RESET=true in backend/.env to enable.

Do NOT enable in production. These endpoints are intentionally destructive.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.corpus_protection import (
    active_database_url,
    corpus_reset_opt_in,
    is_protected_corpus_db,
)
from app.db.database import get_session
from app.db.orm_models import ArticleRow, IngestionRunRow
from app.ingestion.ingestion_service import run_ingestion, _LLM_PROVIDER, _HEBREW_BROAD_SOURCES
from app.models.benchmark import (
    BenchmarkRunResult,
    FallbackStats,
    LLMGatingBenchmarkResponse,
    SourceBenchmarkStats,
    SourceComparison,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Sources the benchmark runs on — only Hebrew broad sources benefit from LLM gating.
_BENCHMARK_SOURCES = sorted(_HEBREW_BROAD_SOURCES)


def _dev_reset_enabled() -> bool:
    return os.environ.get("ALLOW_DEV_RESET", "false").lower() == "true"


def _guard_corpus_db(operation: str, allow_with_opt_in: bool) -> None:
    """Refuse a destructive operation that targets the real article corpus (issue #106).

    The corpus is not in git and cannot be restored. ``ALLOW_DEV_RESET`` alone is
    NOT sufficient authority to destroy it — that boolean is how the 404-article
    corpus was lost on 2026-07-12.

    Args:
        operation: human name of the destructive operation, for the error message.
        allow_with_opt_in: when True, the caller may proceed against the corpus if
            ``ALLOW_CORPUS_DB_RESET=true`` is ALSO set (an explicit, corpus-specific
            second decision). When False, the corpus is refused unconditionally —
            used by the benchmark, which resets RSS data twice per run by design.
    """
    if not is_protected_corpus_db():
        return

    if allow_with_opt_in and corpus_reset_opt_in():
        logger.warning(
            "%s is proceeding against the REAL CORPUS DB (%s) — "
            "ALLOW_CORPUS_DB_RESET=true was explicitly set.",
            operation,
            active_database_url(),
        )
        return

    hint = (
        "Point DATABASE_URL at a copy instead, e.g. "
        "DATABASE_URL=sqlite:///./data/benchmark_copy.db"
    )
    if allow_with_opt_in:
        hint = (
            "If you really mean to destroy the corpus, set ALLOW_CORPUS_DB_RESET=true "
            "(separate from ALLOW_DEV_RESET). Otherwise point DATABASE_URL at a copy."
        )

    raise HTTPException(
        status_code=409,
        detail=(
            f"{operation} refused: DATABASE_URL points at the protected article corpus "
            f"({active_database_url()}). The corpus is not in git and cannot be restored. {hint}"
        ),
    )


def _reset_rss_data(session: Session) -> None:
    """Delete all RSS articles and ingestion run logs (shared by reset + benchmark)."""
    session.query(ArticleRow).filter(ArticleRow.id.like("rss_%")).delete(synchronize_session=False)
    session.query(IngestionRunRow).delete(synchronize_session=False)
    session.commit()


def _count_sport_unknown(session: Session, source_ids: list[str]) -> dict[str, int]:
    """Return per-source count of RSS articles where sport=unknown."""
    rows = (
        session.query(ArticleRow.source, func.count().label("cnt"))
        .filter(
            ArticleRow.id.like("rss_%"),
            ArticleRow.sport == "unknown",
            ArticleRow.source.in_(source_ids),
        )
        .group_by(ArticleRow.source)
        .all()
    )
    return {r.source: r.cnt for r in rows}


def _build_source_stats(
    ingest_result,
    sport_unknown: int,
    gating_enabled: bool,
) -> SourceBenchmarkStats:
    """Convert a SourceIngestResult into a SourceBenchmarkStats for the benchmark response."""
    total_eligible = ingest_result.llm_attempts + ingest_result.llm_skipped
    skip_rate = (
        round(ingest_result.llm_skipped / total_eligible, 4)
        if total_eligible > 0 else None
    )
    return SourceBenchmarkStats(
        total_ms=ingest_result.total_ms or 0.0,
        llm_attempts=ingest_result.llm_attempts,
        llm_successes=ingest_result.llm_successes,
        llm_skipped=ingest_result.llm_skipped,
        skip_rate=skip_rate,
        llm_avg_ms=ingest_result.llm_avg_ms,
        llm_p95_ms=ingest_result.llm_p95_ms,
        fallbacks=FallbackStats(
            connect_error=ingest_result.llm_fallback_connect_error,
            timeout_or_parse=ingest_result.llm_fallback_timeout_or_parse,
            low_confidence=ingest_result.llm_fallback_low_confidence,
        ),
        llm_skip_reasons=ingest_result.llm_skip_reasons,
        llm_call_reasons=ingest_result.llm_call_reasons,
        sport_unknown=sport_unknown,
    )


class ResetRssDataResult(BaseModel):
    status: str
    deleted_articles: int
    deleted_ingestion_runs: int


@router.post("/dev/reset-rss-data", response_model=ResetRssDataResult)
def reset_rss_data(session: Session = Depends(get_session)) -> ResetRssDataResult:
    """Delete all RSS articles (id starts with rss_) and all ingestion run logs.

    Keeps profiles, sources, calibration headlines, feedback events,
    and non-RSS seed articles (id starts with article_).

    Guarded by ALLOW_DEV_RESET=true — returns 403 otherwise.
    """
    if not _dev_reset_enabled():
        raise HTTPException(
            status_code=403,
            detail="Dev reset is disabled. Set ALLOW_DEV_RESET=true in backend/.env to enable.",
        )

    # Issue #106: the corpus needs a SECOND, corpus-specific opt-in — ALLOW_DEV_RESET
    # alone must never be enough to destroy it.
    _guard_corpus_db("reset-rss-data", allow_with_opt_in=True)

    deleted_articles = (
        session.query(ArticleRow)
        .filter(ArticleRow.id.like("rss_%"))
        .delete(synchronize_session=False)
    )
    deleted_runs = session.query(IngestionRunRow).delete(synchronize_session=False)
    session.commit()

    logger.warning(
        "Dev reset executed: deleted %d RSS articles, %d ingestion runs",
        deleted_articles,
        deleted_runs,
    )

    return ResetRssDataResult(
        status="ok",
        deleted_articles=deleted_articles,
        deleted_ingestion_runs=deleted_runs,
    )


@router.post("/dev/benchmark/llm-gating", response_model=LLMGatingBenchmarkResponse)
def run_llm_gating_benchmark(session: Session = Depends(get_session)) -> LLMGatingBenchmarkResponse:
    """Run a two-phase LLM gating benchmark: baseline (gating disabled) then gated (enabled).

    Phase 1 — baseline:
      Reset RSS data, run ingestion for Hebrew broad sources with gating disabled,
      query sport=unknown counts.

    Phase 2 — gated:
      Reset RSS data again, run ingestion with gating enabled, query sport=unknown counts.

    Returns structured comparison so the caller can evaluate skip rate and quality regression.
    Results are not persisted — this is a QA tool only.

    Guarded by ALLOW_DEV_RESET=true (required because each phase resets RSS data).
    Requires an active classification provider (CLASSIFICATION_PROVIDER=ollama or =fake).

    WARNING: Long-running. Each phase takes as long as a full ingestion run
    (~6-12 minutes with Ollama on the baseline phase). Total ~12-20 minutes.
    """
    if not _dev_reset_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Benchmark requires ALLOW_DEV_RESET=true "
                "(it resets RSS data between baseline and gated runs)."
            ),
        )

    # Issue #106: the benchmark resets RSS data TWICE per run by design. It must
    # never be pointed at the real corpus — hard refusal, no override. This is the
    # landmine that would have fired when issue #65 (R7 LLM evaluation) ran.
    _guard_corpus_db("LLM gating benchmark", allow_with_opt_in=False)

    if not _LLM_PROVIDER.can_classify:
        provider_env = os.environ.get("CLASSIFICATION_PROVIDER", "not set")
        raise HTTPException(
            status_code=422,
            detail=(
                f"Classification provider cannot classify (current: CLASSIFICATION_PROVIDER={provider_env!r}). "
                "Set CLASSIFICATION_PROVIDER=ollama (or =fake for testing) and restart the backend."
            ),
        )

    provider_name = os.environ.get("CLASSIFICATION_PROVIDER", "unknown")
    provider_model = os.environ.get("CLASSIFICATION_MODEL", "unknown")
    provider_str = f"{provider_name}:{provider_model}"

    logger.info("LLM gating benchmark starting — provider=%s sources=%s", provider_str, _BENCHMARK_SOURCES)

    # ── Phase 1: baseline — gating disabled ────────────────────────────────────
    logger.info("Benchmark phase 1: resetting RSS data for baseline run")
    _reset_rss_data(session)

    baseline_source_stats: dict[str, SourceBenchmarkStats] = {}
    for src_id in _BENCHMARK_SOURCES:
        logger.info("Benchmark baseline: running %s", src_id)
        results = run_ingestion(session, source_id=src_id, llm_gating_enabled_override=False)
        if results:
            sport_unk = _count_sport_unknown(session, [src_id]).get(src_id, 0)
            baseline_source_stats[src_id] = _build_source_stats(results[0], sport_unk, gating_enabled=False)

    # ── Phase 2: gated — gating enabled ────────────────────────────────────────
    logger.info("Benchmark phase 2: resetting RSS data for gated run")
    _reset_rss_data(session)

    gated_source_stats: dict[str, SourceBenchmarkStats] = {}
    for src_id in _BENCHMARK_SOURCES:
        logger.info("Benchmark gated: running %s", src_id)
        results = run_ingestion(session, source_id=src_id, llm_gating_enabled_override=True)
        if results:
            sport_unk = _count_sport_unknown(session, [src_id]).get(src_id, 0)
            gated_source_stats[src_id] = _build_source_stats(results[0], sport_unk, gating_enabled=True)

    # ── Compute comparison ─────────────────────────────────────────────────────
    comparison: dict[str, SourceComparison] = {}
    for src_id in _BENCHMARK_SOURCES:
        b = baseline_source_stats.get(src_id)
        g = gated_source_stats.get(src_id)
        if b is None or g is None:
            continue
        skip_rate = g.skip_rate or 0.0
        sport_unknown_delta = g.sport_unknown - b.sport_unknown
        comparison[src_id] = SourceComparison(
            llm_call_reduction=b.llm_attempts - g.llm_attempts,
            skip_rate=skip_rate,
            total_ms_reduction=b.total_ms - g.total_ms,
            sport_unknown_delta=sport_unknown_delta,
            passes_targets=(skip_rate >= 0.40 and sport_unknown_delta <= 0),
        )

    logger.info(
        "LLM gating benchmark complete — comparison: %s",
        {s: f"skip={c.skip_rate:.0%} saved={c.llm_call_reduction} Δunknown={c.sport_unknown_delta}"
         for s, c in comparison.items()},
    )

    return LLMGatingBenchmarkResponse(
        provider=provider_str,
        sources=_BENCHMARK_SOURCES,
        baseline=BenchmarkRunResult(gating_enabled=False, sources=baseline_source_stats),
        gated=BenchmarkRunResult(gating_enabled=True, sources=gated_source_stats),
        comparison=comparison,
    )
