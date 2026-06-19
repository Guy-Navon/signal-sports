"""
Orchestrates fetch → filter → classify → dedup → insert for RSS sources.

Design:
- URL and language filters applied at service level (after fetch, before dedup/insert).
- Each source runs independently; one source failing does not abort others.
- Returns a per-source summary (fetched / inserted / skipped_filtered / skipped_duplicate / failed).
- skipped_filtered is live response only — not stored in the DB run log to avoid migration.
- Saves a persisted IngestionRunRecord for every source run.
- Translation: non-Hebrew articles are translated to Hebrew if a provider is configured.
  When translation is disabled (default), original title is preserved as-is.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.classification.merge import merge_with_guardrails
from app.classification.service import get_llm_provider
from app.classification.validation import LLM_MIN_CONFIDENCE
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.adapters.rss_adapter import RSSSourceAdapter
from app.ingestion.classifier import classify, _has_football_maccabi_context
from app.ingestion.config import RSS_SOURCES, RSSSourceConfig, get_source_config, get_enabled_sources
from app.ingestion.dedup import article_id_from_url, url_already_exists
from app.models.article import Article
from app.models.ingestion import IngestionRunRecord, SourceIngestResult
from app.repositories import article_repository, ingestion_repository
from app.translation.language_detection import detect_language
from app.translation.translation_service import translate_title

logger = logging.getLogger(__name__)

# Module-level provider singleton — loaded from env vars at import time
_LLM_PROVIDER = get_llm_provider()

# Sources that route through LLM when the provider is active.
# English basket-only sources (eurohoops, sportando) always use deterministic path.
_HEBREW_BROAD_SOURCES = frozenset({"walla_sport", "israel_hayom_sport"})


# ── URL filter ────────────────────────────────────────────────────────────────

def _should_filter(url: str, cfg: RSSSourceConfig) -> bool:
    """Return True if the item should be skipped based on source config filters."""
    url_lower = url.lower()
    if cfg.blocked_url_patterns:
        if any(pat in url_lower for pat in cfg.blocked_url_patterns):
            return True
    if cfg.allowed_url_patterns:
        if not any(pat in url_lower for pat in cfg.allowed_url_patterns):
            return True
    if cfg.allowed_languages:
        item_lang = detect_language(url, "", cfg.language)
        if item_lang not in cfg.allowed_languages:
            return True
    return False


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalise(
    item: RawSourceItem,
    cfg: RSSSourceConfig,
    llm_available: bool = True,
) -> Article:
    """Map a raw RSS item to an Article using language detection, translation, and classification.

    llm_available=False skips the LLM path for this article (used when the
    per-run circuit breaker has fired due to an Ollama connection error).
    """
    published_at = item.published_at or datetime.now(tz=timezone.utc)

    detected_lang = detect_language(item.url, item.title, cfg.language)

    if detected_lang == "he":
        title = item.title
        original_title = None
        translated_title = None
        classify_title = item.title
    else:
        original_title = item.title
        hebrew = translate_title(item.title, detected_lang)
        translated_title = hebrew
        title = hebrew if hebrew else item.title
        classify_title = title

    # Always run deterministic classifier — used as guardrail source and fallback.
    # Subtitle (item.summary) is passed as additional gap-filling context; title
    # remains the primary signal inside classify().
    subtitle = item.summary  # None if unavailable; already cleaned by rss_adapter
    rules_result = classify(classify_title, source_id=cfg.source_id,
                            language=detected_lang, url=item.url, subtitle=subtitle)

    classified_by = "rules"
    classification_provider: Optional[str] = None
    classification_reason: Optional[str] = None
    classification_confidence: Optional[float] = None
    final_result = rules_result

    # LLM path: Hebrew broad sources only, when provider is active and circuit not open.
    # subtitle is already assigned above; reused here as extra context for the LLM prompt.
    if (
        cfg.source_id in _HEBREW_BROAD_SOURCES
        and _LLM_PROVIDER.can_classify
        and llm_available
    ):
        llm_raw = _LLM_PROVIDER.classify_title(classify_title, detected_lang, subtitle=subtitle)

        if llm_raw is None:
            classified_by = "rules_fallback_after_llm_failure"
            classification_provider = _LLM_PROVIDER.provider_id
        elif llm_raw.confidence < LLM_MIN_CONFIDENCE:
            classified_by = "rules_fallback_low_confidence"
            classification_provider = _LLM_PROVIDER.provider_id
            classification_confidence = llm_raw.confidence
            classification_reason = llm_raw.reason
        else:
            football_maccabi = _has_football_maccabi_context(classify_title.lower())
            final_result, classified_by = merge_with_guardrails(
                llm_raw, rules_result, classify_title.lower(),
                football_maccabi_detected=football_maccabi,
            )
            classification_provider = _LLM_PROVIDER.provider_id
            classification_confidence = llm_raw.confidence
            classification_reason = llm_raw.reason

    return Article(
        id=article_id_from_url(item.url),
        source=cfg.source_id,
        source_display_name=cfg.display_name,
        url=item.url,
        title=title,
        original_title=original_title,
        translated_title=translated_title,
        language=detected_lang,
        published_at=published_at,
        sport=final_result.sport,
        league=final_result.league,
        entities=final_result.entities,
        event_type=final_result.event_type,
        importance=final_result.importance,
        confidence=final_result.confidence,
        tags=final_result.tags,
        classified_by=classified_by,
        classification_provider=classification_provider,
        classification_reason=classification_reason,
        classification_confidence=classification_confidence,
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

    llm_circuit_open = False  # reset per run; fires on Ollama ConnectError only

    for item in items:
        try:
            # Source-level URL and language filters — applied before dedup so filtered
            # items don't pollute the duplicate counters.
            if _should_filter(item.url, cfg):
                skipped_filtered += 1
                logger.debug("Filtered %s (%s)", item.url, cfg.source_id)
                continue

            # URL dedup before translation to avoid paying for duplicate articles
            if url_already_exists(session, item.url):
                skipped_duplicate += 1
                continue

            article = _normalise(item, cfg, llm_available=not llm_circuit_open)

            # Open the circuit for the rest of this run if Ollama refused connection.
            # Timeouts and parse errors do NOT open the circuit (model may recover).
            if (
                not llm_circuit_open
                and article.classified_by == "rules_fallback_after_llm_failure"
                and _LLM_PROVIDER.last_failure_was_connect_error
            ):
                llm_circuit_open = True
                logger.warning(
                    "Ollama connection refused for %s — disabling LLM for rest of this run",
                    cfg.source_id,
                )

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
