from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.db.database import get_session
from app.ingestion.config import RSS_SOURCES, get_source_config
from sqlalchemy import text as sa_text

from app.ingestion.orchestration import (
    TRIGGER_MANUAL,
    TRIGGER_RUN_NOW,
    orchestrate_cycle,
)
from app.ingestion.source_state import get_effective_enabled_map
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


def _ingestion_busy_detail(active_run: Optional[dict]) -> dict:
    """Structured 409 body — identical shape for every guard-protected endpoint.

    ``active_run`` now comes from the DURABLE lease (M7-1, #147): the cycle id,
    heartbeat and owning process of whoever holds the single-flight guard —
    which may be a different process (the scheduler worker), not just this one.
    """
    return {
        "error": "ingestion_already_running",
        "message": "ייבוא פעיל כרגע",
        "active_run": active_run,
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
):
    """Fetch, classify, deduplicate, and insert articles from configured sources.

    Runs through the canonical orchestration service (M7-1, #147): the durable
    DB-backed single-flight guard, a persistent cycle record, and the exact same
    stage ordering as scheduled runs. Returns 409 if another ingestion run
    (manual, run-now, or scheduled — in ANY process) is active.
    """
    outcome = orchestrate_cycle(TRIGGER_MANUAL, source_id=source_id)
    if outcome.skipped:
        raise HTTPException(status_code=409, detail=_ingestion_busy_detail(outcome.active_run))
    results = outcome.source_results
    overall_status = "ok" if all(r.failed == 0 or r.inserted > 0 for r in results) else "error"
    return IngestRunResponse(status=overall_status, sources=results)


@router.get("/ingest/scheduler/status", response_model=SchedulerStatusResponse)
def get_scheduler_status(session: Session = Depends(get_session)):
    """LEGACY-shaped scheduler status, now computed from DURABLE state
    (M7-4, #150). The old in-memory mirror reflected only the API process and
    is gone; this endpoint keeps its response shape for the existing frontend
    while reading the same cycle/lease/worker rows as /api/scheduler/health.
    New consumers should prefer /api/scheduler/health."""
    from datetime import timedelta as _td

    from app.ingestion.orchestration import current_lease, worker_liveness
    from app.worker import read_scheduler_config

    cfg = read_scheduler_config()
    lease = current_lease(session)
    # Runtime truth from the durable worker heartbeat, not the API process env.
    live = worker_liveness(session)

    last = session.execute(sa_text(
        "SELECT started_at, finished_at, status, error_summary, source_results, trigger "
        "FROM scheduler_cycles WHERE status NOT IN ('skipped_active_run') "
        "ORDER BY requested_at DESC LIMIT 1"
    )).fetchone()

    def _dt(iso):
        return datetime.fromisoformat(iso) if iso else None

    # Next run is knowable whenever the worker is genuinely running — gate on
    # the worker heartbeat, never on this process's SCHEDULER_ENABLED env.
    next_run = None
    if live["running"] and live["last_seen_at"]:
        next_run = _dt(live["last_seen_at"]) + _td(seconds=live["interval_seconds"])

    last_status = "never_run"
    summary = None
    if last:
        last_status = "ok" if last[2] in ("succeeded", "succeeded_with_warnings") \
            else ("skipped" if last[2] == "skipped_active_run" else "error")
        if last[4]:
            import json as _json
            parsed = _json.loads(last[4]) if isinstance(last[4], str) else last[4]
            # A cycle can carry JSON-null source_results (json.loads -> None);
            # guard like /api/scheduler/health does, never iterate None.
            summary = [{k: s.get(k) for k in ("source_id", "fetched", "inserted",
                                              "skipped_duplicate", "skipped_filtered",
                                              "failed")} for s in (parsed or [])]

    return SchedulerStatusResponse(
        enabled=cfg.enabled,
        running=bool(live["state"] not in (None, "stopped")),
        worker_running=live["running"],
        automatic_ingestion_active=live["running"],
        interval_minutes=max(1, cfg.interval_seconds // 60),
        next_run_at=next_run,
        last_started_at=_dt(last[0]) if last else None,
        last_finished_at=_dt(last[1]) if last else None,
        last_status=last_status,
        last_error=last[3] if last else None,
        active_run=lease,
        last_result_summary=summary,
    )


@router.post("/ingest/scheduler/run-now", response_model=RunNowResponse)
def scheduler_run_now():
    """Trigger an ingestion run immediately through the canonical orchestration.

    Uses the same durable single-flight guard as manual and scheduled ingestion
    (M7-1, #147); returns 409 if another run — in any process — is active.
    """
    outcome = orchestrate_cycle(TRIGGER_RUN_NOW)
    if outcome.skipped:
        raise HTTPException(status_code=409, detail=_ingestion_busy_detail(outcome.active_run))
    return RunNowResponse(
        trigger="run_now",
        started_at=outcome.started_at,
        finished_at=outcome.finished_at,
        status="ok" if outcome.status in ("succeeded", "succeeded_with_warnings") else "error",
        sources=[
            {
                "source_id": r.source_id,
                "fetched": r.fetched,
                "inserted": r.inserted,
                "skipped_duplicate": r.skipped_duplicate,
                "skipped_filtered": r.skipped_filtered,
                "failed": r.failed,
            }
            for r in outcome.source_results
        ],
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
    from app.worker import read_scheduler_config
    now = datetime.now(tz=timezone.utc)
    interval = max(1, read_scheduler_config().interval_seconds // 60)
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
