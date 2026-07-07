from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.db.database import get_session
from app.ingestion.config import RSS_SOURCES, get_source_config
from app.ingestion.ingestion_service import run_ingestion
from app.ingestion.source_state import get_effective_enabled_map
from app.ingestion.scheduler import (
    run_ingestion_guarded,
    scheduler_state,
)
from app.models.ingestion import (
    IngestQualityResponse,
    IngestRunResponse,
    IngestSourceInfo,
    IngestionRunRecord,
    QuestionableArticle,
    RunNowResponse,
    SchedulerStatusResponse,
    SourceHealthInfo,
)
from app.repositories import ingestion_repository, source_override_repository
from app.repositories.article_repository import get_rss_articles

router = APIRouter()


def _ingestion_busy_detail() -> dict:
    """Structured 409 body — identical shape for every lock-guarded endpoint."""
    return {
        "error": "ingestion_already_running",
        "message": "ייבוא פעיל כרגע",
        "active_run": scheduler_state.active_run,
    }


@router.get("/ingest/sources", response_model=List[IngestSourceInfo])
def list_ingest_sources(session: Session = Depends(get_session)):
    """Return all configured ingest sources (RSS and scraping).

    `enabled` is the effective state: a runtime override (set via
    PATCH /api/ingest/sources/{source_id}) wins over the config.py default.
    """
    enabled_map = get_effective_enabled_map(session)
    return [
        IngestSourceInfo(
            source_id=cfg.source_id,
            display_name=cfg.display_name,
            type=cfg.source_type,
            enabled=enabled_map[cfg.source_id],
            feed_url=cfg.feed_url,
            language=cfg.language,
            is_pilot=cfg.is_pilot,
        )
        for cfg in RSS_SOURCES
    ]


class SourceToggleRequest(BaseModel):
    enabled: bool


@router.patch("/ingest/sources/{source_id}", response_model=IngestSourceInfo)
def set_source_enabled(
    source_id: str,
    payload: SourceToggleRequest,
    session: Session = Depends(get_session),
):
    """Enable/disable a source at runtime (PR 13.1).

    The override is persisted in the source_overrides table, survives restarts,
    and is respected by run-all ingestion, the scheduler, and source health.
    Used by the Sources page toggle (e.g. turning the Sport5 pilot on/off).
    """
    cfg = get_source_config(source_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Unknown source_id: {source_id}")
    source_override_repository.set_override(session, source_id, payload.enabled)
    return IngestSourceInfo(
        source_id=cfg.source_id,
        display_name=cfg.display_name,
        type=cfg.source_type,
        enabled=payload.enabled,
        feed_url=cfg.feed_url,
        language=cfg.language,
        is_pilot=cfg.is_pilot,
    )


@router.post("/ingest/run", response_model=IngestRunResponse)
def run_ingest(
    source_id: Optional[str] = Query(default=None, description="Run a single source by ID; omit for all enabled sources"),
    session: Session = Depends(get_session),
):
    """Fetch, classify, deduplicate, and insert articles from configured sources.

    Returns a per-source summary of fetched / inserted / skipped_filtered / skipped_duplicate / failed counts.
    Returns 409 if another ingestion run (manual, run-now, or scheduled) is active.
    """
    if not scheduler_state.lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail=_ingestion_busy_detail())
    started = datetime.now(tz=timezone.utc)
    scheduler_state.active_run = {"trigger": "manual", "started_at": started.isoformat()}
    scheduler_state.last_started_at = started
    try:
        results = run_ingestion(session, source_id=source_id)
        scheduler_state.last_status = "ok"
        scheduler_state.last_error = None
    except Exception as exc:
        scheduler_state.last_status = "error"
        scheduler_state.last_error = str(exc)
        raise
    finally:
        scheduler_state.last_finished_at = datetime.now(tz=timezone.utc)
        scheduler_state.active_run = None
        scheduler_state.lock.release()
    overall_status = "ok" if all(r.failed == 0 or r.inserted > 0 for r in results) else "error"
    return IngestRunResponse(status=overall_status, sources=results)


@router.get("/ingest/scheduler/status", response_model=SchedulerStatusResponse)
def get_scheduler_status():
    """Live scheduler + ingestion-lock state (PR 13). Not persisted."""
    s = scheduler_state
    return SchedulerStatusResponse(
        enabled=s.enabled,
        running=s.running,
        interval_minutes=s.interval_minutes,
        next_run_at=s.next_run_at,
        last_started_at=s.last_started_at,
        last_finished_at=s.last_finished_at,
        last_status=s.last_status,
        last_error=s.last_error,
        active_run=s.active_run,
        last_result_summary=s.last_result_summary,
    )


@router.post("/ingest/scheduler/run-now", response_model=RunNowResponse)
def scheduler_run_now():
    """Trigger an ingestion run immediately through the internal service path.

    Uses the same process-level lock as manual and scheduled ingestion;
    returns 409 if another run is active.
    """
    summary = run_ingestion_guarded(scheduler_state, trigger="run_now")
    if summary is None:
        raise HTTPException(status_code=409, detail=_ingestion_busy_detail())
    return RunNowResponse(
        trigger="run_now",
        started_at=scheduler_state.last_started_at,
        finished_at=scheduler_state.last_finished_at,
        status=scheduler_state.last_status,
        sources=summary,
    )


def _freshness(
    enabled: bool,
    last_run: Optional[IngestionRunRecord],
    interval_minutes: int,
    now: datetime,
) -> str:
    if not enabled:
        return "disabled"
    if last_run is None:
        return "never_run"
    if last_run.status == "error":
        return "error"
    if now - last_run.started_at > timedelta(minutes=2 * interval_minutes):
        return "stale"
    return "healthy"


@router.get("/ingest/source-health", response_model=List[SourceHealthInfo])
def get_source_health(session: Session = Depends(get_session)):
    """Per-source ingestion health, computed on request from the run log (PR 13).

    Freshness: healthy (successful run within 2x scheduler interval) | stale |
    never_run | disabled | error (latest run failed).
    """
    now = datetime.now(tz=timezone.utc)
    interval = scheduler_state.interval_minutes
    enabled_map = get_effective_enabled_map(session)
    health: list[SourceHealthInfo] = []

    for cfg in RSS_SOURCES:
        runs = ingestion_repository.get_recent_for_source(session, cfg.source_id, limit=20)
        last_run = runs[0] if runs else None

        consecutive_failures = 0
        for run in runs:
            if run.status == "error":
                consecutive_failures += 1
            else:
                break

        effective_enabled = enabled_map[cfg.source_id]
        health.append(SourceHealthInfo(
            source_id=cfg.source_id,
            display_name=cfg.display_name,
            enabled=effective_enabled,
            source_type=cfg.source_type,
            is_pilot=cfg.is_pilot,
            freshness=_freshness(effective_enabled, last_run, interval, now),
            last_run_at=last_run.started_at if last_run else None,
            last_status=last_run.status if last_run else None,
            last_fetched_count=last_run.fetched_count if last_run else None,
            last_inserted_count=last_run.inserted_count if last_run else None,
            last_failed_count=last_run.failed_count if last_run else None,
            last_skipped_duplicate_count=last_run.skipped_duplicate_count if last_run else None,
            consecutive_failures=consecutive_failures,
            last_error_message=last_run.error_message if last_run else None,
        ))

    return health


@router.get("/ingest/runs", response_model=List[IngestionRunRecord])
def list_ingest_runs(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    """Return recent ingestion run records, most recent first."""
    return ingestion_repository.get_recent(session, limit=limit)


@router.get("/ingest/quality", response_model=IngestQualityResponse)
def get_ingest_quality(session: Session = Depends(get_session)):
    """Quality summary for all ingested RSS articles.

    Returns breakdown by sport/league/event_type/importance and a list of
    questionable articles (unknown sport, low confidence, or generic news).
    Useful for tuning the classifier without manually scanning every article.
    """
    articles = get_rss_articles(session)

    sport_breakdown: dict[str, int] = {}
    league_breakdown: dict[str, int] = {}
    event_type_breakdown: dict[str, int] = {}
    importance_breakdown: dict[str, int] = {}
    low_confidence_count = 0
    questionable: list[QuestionableArticle] = []

    for a in articles:
        sport_breakdown[a.sport] = sport_breakdown.get(a.sport, 0) + 1
        league_key = a.league or "unknown"
        league_breakdown[league_key] = league_breakdown.get(league_key, 0) + 1
        event_type_breakdown[a.event_type] = event_type_breakdown.get(a.event_type, 0) + 1
        importance_breakdown[a.importance] = importance_breakdown.get(a.importance, 0) + 1

        if a.confidence < 0.5:
            low_confidence_count += 1

        reasons: list[str] = []
        if a.sport == "unknown":
            reasons.append("sport_unknown")
        if a.confidence < 0.5:
            reasons.append("low_confidence")
        if a.event_type == "news" and not a.entities:
            reasons.append("generic_news")
        if "ambiguous_club" in (a.tags or []):
            reasons.append("ambiguous_club")

        if reasons:
            questionable.append(QuestionableArticle(
                id=a.id,
                title=a.title,
                source=a.source,
                sport=a.sport,
                league=a.league,
                event_type=a.event_type,
                importance=a.importance,
                confidence=a.confidence,
                reasons=reasons,
            ))

    return IngestQualityResponse(
        total_rss_articles=len(articles),
        sport_breakdown=sport_breakdown,
        league_breakdown=league_breakdown,
        event_type_breakdown=event_type_breakdown,
        importance_breakdown=importance_breakdown,
        low_confidence_count=low_confidence_count,
        questionable_articles=questionable,
        # LLM dependency trend (issue #31) — per-run persisted metrics history.
        llm_dependency_runs=ingestion_repository.get_recent(session, limit=20),
    )
