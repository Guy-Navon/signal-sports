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
from app.translation.fake_detection import is_fake_translation
from app.translation.language_detection import detect_language
from app.translation.translation_service import get_provider_status, translate_title

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/translations/status", response_model=TranslationStatusResponse)
def translation_status() -> TranslationStatusResponse:
    """Return the current translation provider configuration."""
    status = get_provider_status()
    return TranslationStatusResponse(**status)


@router.post("/translations/backfill", response_model=BackfillResult)
def backfill_translations(
    limit: Optional[int] = Query(default=None, ge=1, description="Max number of articles to process"),
    source_id: Optional[str] = Query(default=None, description="Limit to a specific source"),
    dry_run: bool = Query(default=False, description="Preview without writing to DB"),
    reclassify: bool = Query(default=True, description="Re-classify using translated title after translation"),
    include_fake: bool = Query(default=False, description="Re-translate fake/stub translations (prefix: תרגום בדיקה:)"),
    force: bool = Query(default=False, description="Re-translate all non-Hebrew articles, even already-translated ones"),
    session: Session = Depends(get_session),
) -> BackfillResult:
    """Translate existing non-Hebrew RSS articles in the database.

    Default behavior: translate articles where translated_title IS NULL.

    include_fake=true: also re-translate articles whose translation is a
    stub from FakeTranslationProvider (title starts with 'תרגום בדיקה:').
    The original_title field is used as the source text so no content is lost.

    force=true: re-translate ALL non-Hebrew articles regardless of existing
    translation.  Uses original_title as source; if original_title is missing
    and the current title is a stub, the article is skipped to avoid data loss.

    Hebrew articles are never touched.
    Running backfill twice in default mode is safe (idempotent).
    """
    provider_status = get_provider_status()
    provider_ready = provider_status["can_translate"]

    all_rss = article_repository.get_rss_articles(session)

    skipped_hebrew = 0
    skipped_already_translated = 0

    # Each candidate is (mode, article):
    #   "normal"  — no translation yet
    #   "fake"    — has stub translation, being re-translated via include_fake
    #   "forced"  — being re-translated via force
    candidates: list[tuple[str, object]] = []

    for article in all_rss:
        if article.language == "he":
            skipped_hebrew += 1
            continue

        if article.translated_title is not None:
            if force:
                candidates.append(("forced", article))
            elif include_fake and is_fake_translation(article.title, article.translated_title):
                candidates.append(("fake", article))
            else:
                skipped_already_translated += 1
        else:
            candidates.append(("normal", article))

    if limit:
        candidates = candidates[:limit]

    if not provider_ready:
        return BackfillResult(
            status="skipped",
            provider_ready=False,
            checked=len(all_rss),
            candidates=len(candidates),
            translated=0,
            retranslated_fake=0,
            forced_retranslated=0,
            skipped_hebrew=skipped_hebrew,
            skipped_already_translated=skipped_already_translated,
            skipped_provider_not_ready=len(candidates),
            language_corrected=0,
            failed=0,
            dry_run=dry_run,
            reason=provider_status.get("reason") or "Translation provider is not configured",
        )

    translated_count = 0
    retranslated_fake_count = 0
    forced_retranslated_count = 0
    failed_count = 0
    skipped_provider_not_ready = 0
    language_corrected = 0
    errors: list[BackfillErrorDetail] = []

    for mode, article in candidates:
        source_title: Optional[str] = None
        try:
            # Prefer original_title as source — it is always the raw RSS title.
            # Fall back to current title only when original is absent AND the
            # current title is not a stub (to avoid translating stub prefixes).
            source_title = article.original_title
            if source_title is None:
                if is_fake_translation(article.title, article.translated_title):
                    logger.warning(
                        "Skipping %s: original_title missing and title is a stub — cannot recover source",
                        article.id,
                    )
                    skipped_provider_not_ready += 1
                    continue
                source_title = article.title

            detected_lang = detect_language(article.url, source_title, article.language)
            lang_changed = detected_lang != article.language

            hebrew = translate_title(source_title, detected_lang)

            if hebrew is None:
                skipped_provider_not_ready += 1
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
                        event_certainty=result.event_certainty,
                    )
            else:
                if lang_changed:
                    language_corrected += 1

            translated_count += 1
            if mode == "fake":
                retranslated_fake_count += 1
            elif mode == "forced":
                forced_retranslated_count += 1

            logger.info(
                "Backfill translated article %s (mode=%s, %s→he): %r → %r",
                article.id, mode, detected_lang, source_title[:60], hebrew[:60],
            )

        except Exception as exc:
            failed_count += 1
            logger.error("Backfill failed for article %s: %s", article.id, exc)
            errors.append(BackfillErrorDetail(
                article_id=article.id,
                title=(source_title or article.title)[:120],
                error=str(exc),
            ))

    overall_status = "ok" if failed_count == 0 else "partial"
    return BackfillResult(
        status=overall_status,
        provider_ready=True,
        checked=len(all_rss),
        candidates=len(candidates),
        translated=translated_count,
        retranslated_fake=retranslated_fake_count,
        forced_retranslated=forced_retranslated_count,
        skipped_hebrew=skipped_hebrew,
        skipped_already_translated=skipped_already_translated,
        skipped_provider_not_ready=skipped_provider_not_ready,
        language_corrected=language_corrected,
        failed=failed_count,
        dry_run=dry_run,
        reason=None,
        errors=errors,
    )
