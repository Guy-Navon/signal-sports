"""
Orchestrates fetch → filter → classify → dedup → insert for RSS sources.

Design:
- URL and language filters applied at service level (after fetch, before dedup/insert).
- Each source runs independently; one source failing does not abort others.
- Returns a per-source summary (fetched / inserted / skipped_filtered / skipped_duplicate / failed).
- skipped_filtered is live response only — not stored in the DB run log to avoid migration.
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


# ── Language inference ────────────────────────────────────────────────────────

# Known URL path segments → ISO 639-1 language code.
# Used to infer the content language when a source mixes languages via URL paths.
_LANG_PATH_MAP: dict[str, str] = {
    "/en/": "en",
    "/tr/": "tr",
    "/es/": "es",
    "/it/": "it",
    "/el/": "el",
    "/de/": "de",
    "/fr/": "fr",
    "/ru/": "ru",
    "/sr/": "sr",
    "/pl/": "pl",
    "/cs/": "cs",
    "/pt/": "pt",
    "/nl/": "nl",
    "/he/": "he",
}


def _infer_language_from_url(url: str, default: str) -> str:
    """Return ISO 639-1 language code inferred from URL path; fall back to default."""
    url_lower = url.lower()
    for path, lang in _LANG_PATH_MAP.items():
        if path in url_lower:
            return lang
    return default


# ── URL filter ────────────────────────────────────────────────────────────────

def _should_filter(url: str, cfg: RSSSourceConfig) -> bool:
    """Return True if the item should be skipped based on source config filters."""
    url_lower = url.lower()
    if cfg.blocked_url_patterns:
        if any(pat in url_lower for pat in cfg.blocked_url_patterns):
            return True
    if cfg.allowed_languages:
        item_lang = _infer_language_from_url(url, cfg.language)
        if item_lang not in cfg.allowed_languages:
            return True
    return False


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalise(item: RawSourceItem, cfg: RSSSourceConfig) -> Article:
    """Map a raw RSS item to an Article using classification results."""
    result = classify(item.title, source_id=cfg.source_id, language=cfg.language, url=item.url)

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
    skipped_filtered = 0
    skipped_duplicate = 0
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
            # Source-level URL and language filters — applied before dedup so filtered
            # items don't pollute the duplicate counters.
            if _should_filter(item.url, cfg):
                skipped_filtered += 1
                logger.debug("Filtered %s (%s)", item.url, cfg.source_id)
                continue

            if url_already_exists(session, item.url):
                skipped_duplicate += 1
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

    # skipped_filtered is intentionally NOT stored in the run log — the DB schema
    # does not have that column and adding it would require a migration.  It is
    # returned in the live API response only.
    run_record = IngestionRunRecord(
        id=str(uuid.uuid4()),
        source_id=cfg.source_id,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        fetched_count=fetched,
        inserted_count=inserted,
        skipped_duplicate_count=skipped_duplicate,
        failed_count=failed,
        error_message=errors[0] if errors else None,
    )
    ingestion_repository.insert(session, run_record)

    return SourceIngestResult(
        source_id=cfg.source_id,
        fetched=fetched,
        inserted=inserted,
        skipped_filtered=skipped_filtered,
        skipped_duplicate=skipped_duplicate,
        failed=failed,
        errors=errors,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def run_ingestion(
    session: Session,
    source_id: Optional[str] = None,
) -> list[SourceIngestResult]:
    """Fetch, filter, classify, deduplicate, and insert articles from RSS sources.

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
                    skipped_filtered=0,
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
            "Ingest %s: fetched=%d filtered=%d inserted=%d skipped=%d failed=%d",
            cfg.source_id, result.fetched, result.skipped_filtered,
            result.inserted, result.skipped_duplicate, result.failed,
        )

    return results
