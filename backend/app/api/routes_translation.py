"""
Translation API routes.

POST /api/translations/backfill  — translate existing non-Hebrew articles in the DB.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.ingestion.classifier import classify
from app.models.translation import BackfillErrorDetail, BackfillResult
from app.repositories import article_repository
from app.translation.language_detection import detect_language
from app.translation.translation_service import translate_title

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/translations/backfill", response_model=BackfillResult)
def backfill_translations(
    limit: Optional[int] = Query(default=None, ge=1, description="Max number of articles to process"),
    source_id: Optional[str] = Query(default=None, description="Limit to a specific source"),
    dry_run: bool = Query(default=False, description="Preview what would be translated without writing"),
    reclassify: bool = Query(default=True, description="Re-classify using translated title after translation"),
    session: Session = Depends(get_session),
) -> BackfillResult:
    """Translate existing non-Hebrew RSS articles in the database.

    Finds articles where:
      - language != 'he'
      - translated_title IS NULL

    For each candidate:
      - Re-detects the true language from URL and title
      - Translates the title to Hebrew
      - Updates title, original_title, translated_title, language
      - Optionally re-classifies using the Hebrew title

    Does not touch Hebrew articles.
    Does not translate articles that already have a translated_title.
    Running backfill twice is safe — already-translated articles are skipped.
    """
    all_rss = article_repository.get_rss_articles(session)

    skipped_hebrew = 0
    skipped_already_translated = 0
    candidates = []

    for article in all_rss:
        if article.language == "he":
            skipped_hebrew += 1
            continue
        if article.translated_title is not None:
            skipped_already_translated += 1
            continue
        candidates.append(article)

    if limit:
        candidates = candidates[:limit]

    translated_count = 0
    failed_count = 0
    errors: list[BackfillErrorDetail] = []

    for article in candidates:
        try:
            detected_lang = detect_language(article.url, article.original_title or article.title, article.language)
            source_title = article.original_title or article.title
            hebrew = translate_title(source_title, detected_lang)

            if hebrew is None:
                # Provider is disabled or returned nothing — skip without error
                logger.debug("Translation skipped (provider noop) for article %s", article.id)
                skipped_already_translated += 1
                continue

            if not dry_run:
                article_repository.update_translation_fields(
                    session,
                    article.id,
                    title=hebrew,
                    original_title=source_title,
                    translated_title=hebrew,
                    language=detected_lang,
                )

                if reclassify:
                    result = classify(hebrew, source_id=article.source, language=detected_lang, url=article.url)
                    article_repository.update_classification_fields(
                        session,
                        article.id,
                        sport=result.sport,
                        league=result.league,
                        entities=result.entities,
                        event_type=result.event_type,
                        importance=result.importance,
                        confidence=result.confidence,
                        tags=result.tags,
                    )

            translated_count += 1
            logger.info("Backfill translated article %s: %r → %r", article.id, source_title[:60], hebrew[:60])

        except Exception as exc:
            failed_count += 1
            logger.error("Backfill failed for article %s: %s", article.id, exc)
            errors.append(BackfillErrorDetail(
                article_id=article.id,
                title=(article.original_title or article.title)[:120],
                error=str(exc),
            ))

    return BackfillResult(
        status="ok" if failed_count == 0 else "partial",
        checked=len(all_rss),
        candidates=len(candidates),
        translated=translated_count,
        skipped_hebrew=skipped_hebrew,
        skipped_already_translated=skipped_already_translated,
        failed=failed_count,
        dry_run=dry_run,
        errors=errors,
    )
