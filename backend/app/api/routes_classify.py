"""
Classification API routes.

GET  /api/classify/status   — current provider configuration
POST /api/classify/backfill — reclassify existing Hebrew broad source articles with LLM
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.classification.facts import build_article_facts
from app.classification.merge import merge_with_guardrails, normalize_league_sport_compatibility
from app.classification.service import get_llm_provider
from app.classification.source_hints import extract_source_sport_hint
from app.classification.validation import LLM_MIN_CONFIDENCE
from app.db.database import get_session
from app.ingestion.classifier import classify, _has_football_maccabi_context
from app.repositories import article_repository

logger = logging.getLogger(__name__)

router = APIRouter()

# Hebrew broad sources eligible for LLM reclassification
_HEBREW_BROAD_SOURCES = frozenset({
    "walla_sport",
    "israel_hayom_sport",
    "ynet_sport",
    "one_sport",
    "sport5_sport",
})


class ClassifyStatusResponse(BaseModel):
    provider: str
    can_classify: bool
    hebrew_broad_sources: list[str]
    model: Optional[str] = None
    base_url: Optional[str] = None
    reset_allowed: bool = False


class ClassifyBackfillResult(BaseModel):
    provider: str
    processed: int
    llm_classified: int
    guardrail_corrections: int
    fallback_count: int
    low_confidence_count: int
    skipped_already_classified: int
    skipped_provider_not_ready: int
    dry_run: bool


@router.get("/classify/status", response_model=ClassifyStatusResponse)
def classify_status() -> ClassifyStatusResponse:
    """Return the current classification provider configuration."""
    provider = get_llm_provider()
    model = os.environ.get("CLASSIFICATION_MODEL") or None
    base_url = os.environ.get("CLASSIFICATION_OLLAMA_BASE_URL") or None
    reset_allowed = os.environ.get("ALLOW_DEV_RESET", "false").lower() == "true"
    return ClassifyStatusResponse(
        provider=provider.provider_id,
        can_classify=provider.can_classify,
        hebrew_broad_sources=sorted(_HEBREW_BROAD_SOURCES),
        model=model,
        base_url=base_url,
        reset_allowed=reset_allowed,
    )


@router.post("/classify/backfill", response_model=ClassifyBackfillResult)
def classify_backfill(
    source_id: Optional[str] = Query(default=None, description="Limit to one source"),
    limit: Optional[int] = Query(default=None, ge=1, description="Max articles to process"),
    dry_run: bool = Query(default=False, description="Preview without writing to DB"),
    force: bool = Query(default=False, description="Reclassify all articles, even already LLM-classified"),
    session: Session = Depends(get_session),
) -> ClassifyBackfillResult:
    """Reclassify existing Hebrew broad source articles using the LLM provider.

    Default (force=False): skips articles with classified_by in {'llm', 'llm+rules_guardrail'}.
    force=True: reclassifies ALL articles from Hebrew broad sources regardless of current state.

    Updates all classification fields (sport, league, entities, event_type, importance,
    confidence, tags) as well as classification metadata fields.

    source_id filter is applied at the DB query level (not post-filter in Python).
    """
    provider = get_llm_provider()

    target_sources = (
        [source_id] if source_id and source_id in _HEBREW_BROAD_SOURCES
        else list(_HEBREW_BROAD_SOURCES)
    )

    if source_id and source_id not in _HEBREW_BROAD_SOURCES:
        logger.warning(
            "classify/backfill: source_id=%r is not a Hebrew broad source; nothing to do",
            source_id,
        )

    candidates = article_repository.get_articles_for_classification_backfill(
        session,
        source_ids=target_sources,
        force=force,
        limit=limit,
    )

    skipped_already_classified = 0
    if not force:
        # Count separately for reporting — the query already filtered them out
        all_from_sources = article_repository.get_articles_for_classification_backfill(
            session,
            source_ids=target_sources,
            force=True,
        )
        skipped_already_classified = len(all_from_sources) - len(candidates)
        if limit:
            skipped_already_classified = max(0, skipped_already_classified)

    if not provider.can_classify:
        return ClassifyBackfillResult(
            provider=provider.provider_id,
            processed=0,
            llm_classified=0,
            guardrail_corrections=0,
            fallback_count=0,
            low_confidence_count=0,
            skipped_already_classified=skipped_already_classified,
            skipped_provider_not_ready=len(candidates),
            dry_run=dry_run,
        )

    llm_classified = 0
    guardrail_corrections = 0
    fallback_count = 0
    low_confidence_count = 0

    for article in candidates:
        classify_title = article.title
        source_sport_hint = extract_source_sport_hint(article.source, article.url)

        rules_result = classify(
            classify_title,
            source_id=article.source,
            language=article.language,
            url=article.url,
            subtitle=article.subtitle,
            source_sport_hint=source_sport_hint,
        )

        llm_raw = provider.classify_title(classify_title, article.language)

        if llm_raw is None:
            classified_by = "rules_fallback_after_llm_failure"
            final_result = rules_result
            classification_provider = provider.provider_id
            classification_reason = None
            classification_confidence = None
            fallback_count += 1
        elif llm_raw.confidence < LLM_MIN_CONFIDENCE:
            classified_by = "rules_fallback_low_confidence"
            final_result = rules_result
            classification_provider = provider.provider_id
            classification_reason = llm_raw.reason
            classification_confidence = llm_raw.confidence
            low_confidence_count += 1
        else:
            football_maccabi = _has_football_maccabi_context(classify_title.lower())
            final_result, classified_by = merge_with_guardrails(
                llm_raw, rules_result, classify_title.lower(),
                football_maccabi_detected=football_maccabi,
            )
            classification_provider = provider.provider_id
            classification_reason = llm_raw.reason
            classification_confidence = llm_raw.confidence
            llm_classified += 1
            if classified_by == "llm+rules_guardrail":
                guardrail_corrections += 1

        # Defense-in-depth parity with ingestion, then the ArticleFacts stage.
        final_result = normalize_league_sport_compatibility(final_result)
        facts = build_article_facts(
            title=classify_title,
            subtitle=article.subtitle,
            url=article.url,
            source_id=article.source,
            source_sport_hint=source_sport_hint,
            result=final_result,
            llm_raw=llm_raw,
            gate_should_call=None,
            gate_reason=None,
            classified_by=classified_by,
        )

        if not dry_run:
            article_repository.update_full_classification(
                session,
                article.id,
                sport=facts.sport,
                league=facts.league,
                entities=facts.entities,
                event_type=final_result.event_type,
                importance=final_result.importance,
                confidence=final_result.confidence,
                tags=final_result.tags,
                classified_by=classified_by,
                classification_provider=classification_provider,
                classification_reason=classification_reason,
                classification_confidence=classification_confidence,
                primary_competition=facts.primary_competition,
                article_competitions=facts.article_competitions,
                entity_ids=facts.entity_ids,
                classification_trace=facts.trace,
                taxonomy_version=facts.taxonomy_version,
            )

        logger.info(
            "Backfill classify %s (%s): %s → sport=%s league=%s event=%s",
            article.id, classified_by, classify_title[:60],
            final_result.sport, final_result.league, final_result.event_type,
        )

    return ClassifyBackfillResult(
        provider=provider.provider_id,
        processed=len(candidates),
        llm_classified=llm_classified,
        guardrail_corrections=guardrail_corrections,
        fallback_count=fallback_count,
        low_confidence_count=low_confidence_count,
        skipped_already_classified=skipped_already_classified,
        skipped_provider_not_ready=0,
        dry_run=dry_run,
    )
