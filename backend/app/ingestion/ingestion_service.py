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
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.classification.gating import LLMGateDecision, should_call_llm_for_article
from app.classification.merge import merge_with_guardrails, normalize_league_sport_compatibility
from app.classification.source_hints import extract_source_sport_hint
from app.classification.service import get_llm_provider
from app.classification.validation import LLM_MIN_CONFIDENCE
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.adapters.rss_adapter import RSSSourceAdapter
from app.ingestion.classifier import (
    classify,
    _has_football_maccabi_context,
    has_maccabi_tel_aviv_phrase,
    compute_importance,
    enrich_maccabi_entity_after_sport_resolve,
)
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
    llm_gating_enabled_override: Optional[bool] = None,
) -> tuple[Article, Optional[float], Optional[LLMGateDecision]]:
    """Map a raw RSS item to an Article using language detection, translation, and classification.

    Returns (article, llm_ms, gate) where:
    - llm_ms is the LLM call duration in milliseconds if an LLM attempt was made
      (including failed attempts), or None if LLM was not invoked.
    - gate is the LLMGateDecision for eligible articles (Hebrew broad source + provider
      active + circuit not open), or None for non-eligible articles.
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
    # Source URL category hint: authoritative for sources with structured URL categories
    # (e.g. Israel Hayom /sport/israeli-basketball/). None for all other sources.
    source_sport_hint = extract_source_sport_hint(cfg.source_id, item.url)
    rules_result = classify(classify_title, source_id=cfg.source_id,
                            language=detected_lang, url=item.url, subtitle=subtitle,
                            source_sport_hint=source_sport_hint)

    classified_by = "rules"
    classification_provider: Optional[str] = None
    classification_reason: Optional[str] = None
    classification_confidence: Optional[float] = None
    final_result = rules_result

    # LLM path: Hebrew broad sources only, when provider is active and circuit not open.
    # subtitle is already assigned above; reused here as extra context for the LLM prompt.
    llm_ms: Optional[float] = None
    gate: Optional[LLMGateDecision] = None

    if (
        cfg.source_id in _HEBREW_BROAD_SOURCES
        and _LLM_PROVIDER.can_classify
        and llm_available
    ):
        gate = should_call_llm_for_article(
            source_id=cfg.source_id,
            title=classify_title,
            subtitle=subtitle,
            rules_result=rules_result,
            source_sport_hint=source_sport_hint,
            gating_enabled_override=llm_gating_enabled_override,
        )

        if not gate.should_call_llm:
            logger.debug(
                "LLM gated-skip [%s] reason=%s title=%r sport=%s league=%s "
                "event_type=%s conf=%.2f",
                cfg.source_id, gate.reason, classify_title[:60],
                rules_result.sport, rules_result.league,
                rules_result.event_type, rules_result.confidence,
            )
        else:
            _t0 = time.perf_counter()
            llm_raw = _LLM_PROVIDER.classify_title(classify_title, detected_lang, subtitle=subtitle)
            llm_ms = (time.perf_counter() - _t0) * 1000

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
                    source_sport_hint=source_sport_hint,
                )
                classification_provider = _LLM_PROVIDER.provider_id
                classification_confidence = llm_raw.confidence
                classification_reason = llm_raw.reason

    # Final league-sport compatibility normalisation — applies to both rules-only and LLM-merge
    # paths so no Article can be persisted with an impossible sport/league combination.
    final_result = normalize_league_sport_compatibility(final_result)

    # Post-merge Maccabi entity injection:
    # classify() cannot assign the Maccabi Tel Aviv Basketball entity when the title has the
    # full-name club form but no sport context (ambiguous_club). If LLM resolved sport to
    # basketball, we inject the entity now so the article reaches Guy's Maccabi topic.
    title_lower = classify_title.lower()
    enriched_entities = enrich_maccabi_entity_after_sport_resolve(
        final_result.entities, title_lower, final_result.sport
    )
    if enriched_entities is not final_result.entities:
        final_result.entities = enriched_entities
        final_result.tags = [t for t in final_result.tags if t != "ambiguous_club"]
        if "Maccabi Tel Aviv Basketball" not in final_result.tags:
            final_result.tags = [*final_result.tags, "Maccabi Tel Aviv Basketball"]
        final_result.importance = compute_importance(
            final_result.event_type, final_result.entities, final_result.league
        )

    article = Article(
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
        subtitle=subtitle,
        classified_by=classified_by,
        classification_provider=classification_provider,
        classification_reason=classification_reason,
        classification_confidence=classification_confidence,
    )
    return article, llm_ms, gate


# ── Per-source run ────────────────────────────────────────────────────────────

def _run_source(
    session: Session,
    cfg: RSSSourceConfig,
    llm_gating_enabled_override: Optional[bool] = None,
) -> SourceIngestResult:
    _run_t0 = time.perf_counter()
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

    # Timing accumulators — local only; computed stats go into SourceIngestResult.
    _fetch_ms: Optional[float] = None
    _llm_latencies: list[float] = []           # ms per LLM attempt (success or failure)
    _llm_title_samples: list[tuple[str, float]] = []  # (title_snippet, ms) for slowest logging
    llm_attempts = 0
    llm_successes = 0
    llm_fallback_connect_error = 0
    llm_fallback_timeout_or_parse = 0
    llm_fallback_low_confidence = 0
    # Gating accumulators — eligible articles skipped/called by the gate.
    llm_skipped = 0
    llm_skip_reasons: dict[str, int] = {}
    llm_call_reasons: dict[str, int] = {}

    items: list[RawSourceItem] = []
    try:
        _fetch_t0 = time.perf_counter()
        items = adapter.fetch()
        _fetch_ms = (time.perf_counter() - _fetch_t0) * 1000
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

            article, llm_ms, gate = _normalise(
                item, cfg,
                llm_available=not llm_circuit_open,
                llm_gating_enabled_override=llm_gating_enabled_override,
            )

            # Accumulate LLM timing and counters.
            if llm_ms is not None:
                _llm_latencies.append(llm_ms)
                _llm_title_samples.append((item.title[:50], llm_ms))
                cb = article.classified_by
                if cb in ("llm", "llm+rules_guardrail"):
                    llm_attempts += 1
                    llm_successes += 1
                elif cb == "rules_fallback_after_llm_failure":
                    llm_attempts += 1
                    if _LLM_PROVIDER.last_failure_was_connect_error:
                        llm_fallback_connect_error += 1
                    else:
                        llm_fallback_timeout_or_parse += 1
                elif cb == "rules_fallback_low_confidence":
                    llm_attempts += 1
                    llm_fallback_low_confidence += 1

            # Accumulate gating counters — only for eligible articles (gate is not None).
            # Non-eligible articles (non-Hebrew-broad source, provider disabled, circuit open)
            # never set gate, so they never appear in llm_skipped.
            if gate is not None:
                if gate.should_call_llm:
                    llm_call_reasons[gate.reason] = llm_call_reasons.get(gate.reason, 0) + 1
                else:
                    llm_skipped += 1
                    llm_skip_reasons[gate.reason] = llm_skip_reasons.get(gate.reason, 0) + 1

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
    total_ms = (time.perf_counter() - _run_t0) * 1000
    status = "error" if errors and inserted == 0 else "ok"

    # Compute LLM latency stats from local accumulators.
    llm_avg_ms: Optional[float] = None
    llm_p95_ms: Optional[float] = None
    if _llm_latencies:
        llm_avg_ms = round(sum(_llm_latencies) / len(_llm_latencies), 1)
        sorted_lat = sorted(_llm_latencies)
        p95_idx = min(len(sorted_lat) - 1, math.ceil(0.95 * len(sorted_lat)) - 1)
        llm_p95_ms = round(sorted_lat[p95_idx], 1)
        slowest = sorted(_llm_title_samples, key=lambda x: x[1], reverse=True)[:5]
        slowest_str = ", ".join(f'"{t}"({ms:.0f}ms)' for t, ms in slowest)
    else:
        slowest_str = "n/a"

    logger.info(
        "Timing [%s]: fetch=%.0fms total=%.0fms | "
        "LLM: attempts=%d successes=%d avg=%s p95=%s | "
        "Fallbacks: connect_error=%d timeout/parse=%d low_conf=%d | "
        "Gating: skipped=%d skip_reasons=%s call_reasons=%s | "
        "Slowest: [%s]",
        cfg.source_id,
        _fetch_ms or 0,
        total_ms,
        llm_attempts,
        llm_successes,
        f"{llm_avg_ms:.0f}ms" if llm_avg_ms is not None else "n/a",
        f"{llm_p95_ms:.0f}ms" if llm_p95_ms is not None else "n/a",
        llm_fallback_connect_error,
        llm_fallback_timeout_or_parse,
        llm_fallback_low_confidence,
        llm_skipped,
        llm_skip_reasons or "{}",
        llm_call_reasons or "{}",
        slowest_str,
    )

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
        fetch_ms=round(_fetch_ms, 1) if _fetch_ms is not None else None,
        total_ms=round(total_ms, 1),
        llm_attempts=llm_attempts,
        llm_successes=llm_successes,
        llm_fallback_connect_error=llm_fallback_connect_error,
        llm_fallback_timeout_or_parse=llm_fallback_timeout_or_parse,
        llm_fallback_low_confidence=llm_fallback_low_confidence,
        llm_avg_ms=llm_avg_ms,
        llm_p95_ms=llm_p95_ms,
        llm_skipped=llm_skipped,
        llm_skip_reasons=llm_skip_reasons,
        llm_call_reasons=llm_call_reasons,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def run_ingestion(
    session: Session,
    source_id: Optional[str] = None,
    llm_gating_enabled_override: Optional[bool] = None,
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
        result = _run_source(session, cfg, llm_gating_enabled_override=llm_gating_enabled_override)
        results.append(result)
        logger.info(
            "Ingest %s: fetched=%d filtered=%d inserted=%d skipped=%d failed=%d",
            cfg.source_id, result.fetched, result.skipped_filtered,
            result.inserted, result.skipped_duplicate, result.failed,
        )

    return results
