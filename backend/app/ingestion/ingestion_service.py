"""
Orchestrates fetch → classify → dedup → insert for RSS sources.

Design:
- Each source runs independently; one source failing does not abort others.
- Returns a per-source summary (fetched / inserted / skipped / failed).
- Saves a persisted IngestionRunRecord for every source run.
- Does NOT perform translation — translated_title remains None for now.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.adapters.rss_adapter import RSSSourceAdapter
from app.ingestion.classifier import classify
from app.ingestion.config import RSS_SOURCES, RSSSourceConfig, get_source_config, get_enabled_sources
from app.ingestion.dedup import article_id_from_url, url_already_exists
from app.models.article import Article
from app.models.ingestion import IngestionRunRecord, SourceIngestResult
from app.repositories import article_repository, ingestion_repository

logger = logging.getLogger(__name__)


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalise(item: RawSourceItem, cfg: RSSSourceConfig) -> Article:
    """Map a raw RSS item to an Article using classification results."""
    result = classify(item.title, source_id=cfg.source_id, language=cfg.language)

    published_at = item.published_at or datetime.now(tz=timezone.utc)

    if cfg.language == "he":
        original_title = None
        translated_title = None
    else:
        original_title = item.title
        translated_title = None   # translation deferred

    return Article(
        id=article_id_from_url(item.url),
        source=cfg.source_id,
        source_display_name=cfg.display_name,
        url=item.url,
        title=item.title,
        original_title=original_title,
        translated_title=translated_title,
        language=cfg.language,
        published_at=published_at,
        sport=result.sport,
        league=result.league,
        entities=result.entities,
        event_type=result.event_type,
        importance=result.importance,
        confidence=result.confidence,
        tags=result.tags,
    )


# ── Per-source run ────────────────────────────────────────────────────────────

def _run_source(session: Session, cfg: RSSSourceConfig) -> SourceIngestResult:
    started_at = datetime.now(tz=timezone.utc)
    adapter = RSSSourceAdapter(
        source_id=cfg.source_id,
        feed_url=cfg.feed_url,
        source_display_name=cfg.display_name,
        language=cfg.language,
    )

    fetched = 0
    inserted = 0
    skipped = 0
    failed = 0
    errors: list[str] = []

    items: list[RawSourceItem] = []
    try:
        items = adapter.fetch()
        fetched = len(items)
    except Exception as exc:
        msg = f"Fetch error for {cfg.source_id}: {exc}"
        logger.error(msg)
        errors.append(msg)

    for item in items:
        try:
            if url_already_exists(session, item.url):
                skipped += 1
                continue
            article = _normalise(item, cfg)
            article_repository.insert(session, article)
            inserted += 1
        except Exception as exc:
            msg = f"Item error [{item.url}]: {exc}"
            logger.error(msg)
            errors.append(msg)
            failed += 1

    finished_at = datetime.now(tz=timezone.utc)
    status = "error" if errors and inserted == 0 else "ok"

    run_record = IngestionRunRecord(
        id=str(uuid.uuid4()),
        source_id=cfg.source_id,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        fetched_count=fetched,
        inserted_count=inserted,
        skipped_duplicate_count=skipped,
        failed_count=failed,
        error_message=errors[0] if errors else None,
    )
    ingestion_repository.insert(session, run_record)

    return SourceIngestResult(
        source_id=cfg.source_id,
        fetched=fetched,
        inserted=inserted,
        skipped_duplicate=skipped,
        failed=failed,
        errors=errors,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def run_ingestion(
    session: Session,
    source_id: Optional[str] = None,
) -> list[SourceIngestResult]:
    """Fetch, classify, deduplicate, and insert articles from RSS sources.

    Args:
        session:   SQLAlchemy session for DB access.
        source_id: If given, run only that source; otherwise run all enabled sources.

    Returns:
        One SourceIngestResult per source that was attempted.
    """
    if source_id:
        cfg = get_source_config(source_id)
        if cfg is None:
            return [
                SourceIngestResult(
                    source_id=source_id,
                    fetched=0,
                    inserted=0,
                    skipped_duplicate=0,
                    failed=0,
                    errors=[f"Unknown source_id: {source_id}"],
                )
            ]
        configs = [cfg]
    else:
        configs = get_enabled_sources()

    results: list[SourceIngestResult] = []
    for cfg in configs:
        result = _run_source(session, cfg)
        results.append(result)
        logger.info(
            "Ingest %s: fetched=%d inserted=%d skipped=%d failed=%d",
            cfg.source_id, result.fetched, result.inserted,
            result.skipped_duplicate, result.failed,
        )

    return results
