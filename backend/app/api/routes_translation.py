"""
Translation API routes.

GET  /api/translations/status   — current provider configuration
POST /api/translations/backfill — translate existing non-Hebrew articles in the DB
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.ingestion.classifier import classify
from app.models.translation import (
    BackfillErrorDetail,
    BackfillResult,
    TranslationStatusResponse,
)
from app.repositories import article_repository
from app.translation.language_detection import detect_language
from app.translation.translation_service import get_provider_status, translate_title

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/translations/status", response_model=TranslationStatusResponse)
def translation_status() -> TranslationStatusResponse:
    """Return the current translation provider configuration.

    Useful for the UI to show whether translation is active, and if not, why.
    """
    status = get_provider_status()
    return TranslationStatusResponse(**status)


@router.post("/translations/backfill", response_model=BackfillResult)
def backfill_translations(
    limit: Optional[int] = Query(default=None, ge=1, description="Max number of articles to process"),
    source_id: Optional[str] = Query(default=None, description="Limit to a specific source"),
    dry_run: bool = Query(default=False, description="Preview without writing to DB"),
    reclassify: bool = Query(default=True, description="Re-classify using translated title after translation"),
    session: Session = Depends(get_session),
) -> BackfillResult:
    """Translate existing non-Hebrew RSS articles in the database.

    Candidate articles: language != 'he' AND translated_title IS NULL.

    For each candidate:
      1. Re-detects the true language from URL and title (corrects mislabeled articles).
      2. If provider can translate: translates and updates title/original_title/translated_title/language.
      3. Optionally re-classifies using the Hebrew title.

    Hebrew articles are never touched.
    Already-translated articles are skipped.
    Running backfill twice is safe.

    Language correction (step 1) is performed even when the translation provider is
    disabled — this corrects mislabeled language fields (e.g. Italian Sportando
    articles stored as 'en') without requiring a real translation API.
    """
    provider_status = get_provider_status()
    provider_ready = provider_status["can_translate"]

    all_rss = article_repository.get_rss_articles(session)

    skipped_hebrew = 0
    skipped_already_translated = 0
    skipped_provider_not_ready = 0
    language_corrected = 0
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

    # If provider cannot translate, return early with a clear explanation.
    # We still report the candidate count so the UI can show how many articles
    # would be translated once a provider is configured.
    if not provider_ready:
        return BackfillResult(
            status="skipped",
            provider_ready=False,
            checked=len(all_rss),
            candidates=len(candidates),
            translated=0,
            skipped_hebrew=skipped_hebrew,
            skipped_already_translated=skipped_already_translated,
            skipped_provider_not_ready=len(candidates),
            language_corrected=0,
            failed=0,
            dry_run=dry_run,
            reason=provider_status.get("reason") or "Translation provider is not configured",
        )

    translated_count = 0
    failed_count = 0
    errors: list[BackfillErrorDetail] = []

    for article in candidates:
        try:
            source_title = article.original_title or article.title
            detected_lang = detect_language(article.url, source_title, article.language)

            # Track language correction even if translation is skipped
            lang_changed = (detected_lang != article.language)

            hebrew = translate_title(source_title, detected_lang)

            if hebrew is None:
                # Provider active but returned nothing for this article
                skipped_provider_not_ready += 1
                # Still correct the language if detection changed it
                if lang_changed and not dry_run:
                    article_repository.update_translation_fields(
                        session,
                        article.id,
                        title=source_title,
                        original_title=source_title,
                        translated_title=None,
                        language=detected_lang,
                    )
                    language_corrected += 1
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
                if lang_changed:
                    language_corrected += 1

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
            else:
                if lang_changed:
                    language_corrected += 1

            translated_count += 1
            logger.info(
                "Backfill translated article %s (%s→he): %r → %r",
                article.id, detected_lang, source_title[:60], hebrew[:60],
            )

        except Exception as exc:
            failed_count += 1
            logger.error("Backfill failed for article %s: %s", article.id, exc)
            errors.append(BackfillErrorDetail(
                article_id=article.id,
                title=source_title[:120],
                error=str(exc),
            ))

    overall_status = "ok" if failed_count == 0 else "partial"
    return BackfillResult(
        status=overall_status,
        provider_ready=True,
        checked=len(all_rss),
        candidates=len(candidates),
        translated=translated_count,
        skipped_hebrew=skipped_hebrew,
        skipped_already_translated=skipped_already_translated,
        skipped_provider_not_ready=skipped_provider_not_ready,
        language_corrected=language_corrected,
        failed=failed_count,
        dry_run=dry_run,
        reason=None,
        errors=errors,
    )
