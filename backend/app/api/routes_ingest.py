from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.ingestion.config import get_enabled_sources, RSS_SOURCES
from app.ingestion.ingestion_service import run_ingestion
from app.models.ingestion import (
    IngestRunResponse,
    IngestSourceInfo,
    IngestionRunRecord,
)
from app.repositories import ingestion_repository

router = APIRouter()


@router.get("/ingest/sources", response_model=List[IngestSourceInfo])
def list_ingest_sources():
    """Return all configured RSS ingest sources."""
    return [
        IngestSourceInfo(
            source_id=cfg.source_id,
            display_name=cfg.display_name,
            type="rss",
            enabled=cfg.enabled,
            feed_url=cfg.feed_url,
        )
        for cfg in RSS_SOURCES
    ]


@router.post("/ingest/run", response_model=IngestRunResponse)
def run_ingest(
    source_id: Optional[str] = Query(default=None, description="Run a single source by ID; omit for all enabled sources"),
    session: Session = Depends(get_session),
):
    """Fetch, classify, deduplicate, and insert articles from RSS sources.

    Returns a per-source summary of fetched / inserted / skipped / failed counts.
    """
    results = run_ingestion(session, source_id=source_id)
    overall_status = "ok" if all(r.failed == 0 or r.inserted > 0 for r in results) else "error"
    return IngestRunResponse(status=overall_status, sources=results)


@router.get("/ingest/runs", response_model=List[IngestionRunRecord])
def list_ingest_runs(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    """Return recent ingestion run records, most recent first."""
    return ingestion_repository.get_recent(session, limit=limit)
