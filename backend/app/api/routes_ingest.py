from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.ingestion.config import get_enabled_sources, RSS_SOURCES
from app.ingestion.ingestion_service import run_ingestion
from app.models.ingestion import (
    IngestQualityResponse,
    IngestRunResponse,
    IngestSourceInfo,
    IngestionRunRecord,
    QuestionableArticle,
)
from app.repositories import ingestion_repository
from app.repositories.article_repository import get_rss_articles

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

    Returns a per-source summary of fetched / inserted / skipped_filtered / skipped_duplicate / failed counts.
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
    )
