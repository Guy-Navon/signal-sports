"""
Merge LLM classification result with deterministic rules result.

Strategy: LLM primary. Rules fire only as guardrails for known failure modes.
Entities from rules are canonical (required for relevance engine string matching);
LLM entities go through the normalization map and any recognized ones are appended.
"""

import logging
from typing import Optional

from app.classification.entity_normalizer import normalize_llm_entities, prune_sport_incompatible_entities
from app.classification.llm_result import LLMClassificationResult
from app.ingestion.classifier import ClassificationResult, _assign_confidence, _collect_tags, _has

logger = logging.getLogger(__name__)

_IMPORTANCE_RANK = {"very_high": 4, "high": 3, "medium": 2, "low": 1}

# ── Guardrail 4b: LLM title_win evidence check ────────────────────────────────

# At least one of these must appear in the title for an LLM title_win claim to be accepted.
# "גמר" is intentionally excluded: a final ≠ a title win.
_TITLE_WIN_EVIDENCE_KW = (
    "אלוף", "אלופה", "אלופת", "אלופות",
    "הניפה", "הניף",            # lifted/raised a trophy
    "champion", "champions", "title", "trophy", "clinches", "clinched",
    "בגביע", "הגביע", "גביע",
    "בתואר", "תואר",
    "באליפות",
)

# ── League-sport compatibility ─────────────────────────────────────────────────

# Basketball leagues: if final league is one of these, sport MUST be basketball.
_BASKETBALL_LEAGUES = frozenset({
    "EuroLeague", "EuroCup", "NBA",
    "Spanish ACB", "Turkish BSL", "Greek Basket League",
    "Italian LBA", "French LNB", "Israeli Basketball League",
})
# Football-only leagues: if final league is one of these, sport MUST be football.
# Intentionally conservative — only currently valid league names in this PR.
_FOOTBALL_ONLY_LEAGUES = frozenset({
    "Israeli Premier League",
})


def normalize_league_sport_compatibility(result: ClassificationResult) -> ClassificationResult:
    """Correct impossible sport/league combinations. Idempotent — safe to call for all paths.

    Called in ingestion_service.py after final classification (rules-only and LLM-merge)
    to guarantee no Article is persisted with an invalid sport/league pair.
    """
    if result.league is None:
        return result
    corrected_sport = result.sport
    if result.league in _BASKETBALL_LEAGUES and result.sport != "basketball":
        logger.warning(
            "League-sport compat: %r is a basketball league, correcting sport %r → basketball",
            result.league, result.sport,
        )
        corrected_sport = "basketball"
    elif result.league in _FOOTBALL_ONLY_LEAGUES and result.sport != "football":
        logger.warning(
            "League-sport compat: %r is a football league, correcting sport %r → football",
            result.league, result.sport,
        )
        corrected_sport = "football"
    if corrected_sport == result.sport:
        return result
    return ClassificationResult(
        sport=corrected_sport,
        league=result.league,
        entities=result.entities,
        event_type=result.event_type,
        importance=result.importance,
        confidence=result.confidence,
        tags=result.tags,
    )


def merge_with_guardrails(
    llm: LLMClassificationResult,
    rules: ClassificationResult,
    title_lower: str,
    football_maccabi_detected: bool = False,
    source_sport_hint: Optional[str] = None,
) -> tuple[ClassificationResult, str]:
    """
    Returns (final ClassificationResult, classified_by string).
    LLM wins on all fields except where guardrails fire.
    """
    sport = llm.sport
    league = llm.league
    event_type = llm.event_type
    importance = llm.importance
    guardrail_fired = False

    # Guardrail 1: Football Maccabi clubs (deterministic, high precision)
    # Rules detected an explicit football Maccabi club keyword — LLM must not override.
    if football_maccabi_detected and sport != "football":
        sport = "football"
        league = rules.league
        guardrail_fired = True
        logger.debug("Guardrail 1 fired: football Maccabi detected, overriding LLM sport")

    # Guardrail 2: LLM says sport=unknown but rules found a sport — use rules
    if sport == "unknown" and rules.sport != "unknown":
        sport = rules.sport
        guardrail_fired = True

    # Guardrail 3: LLM returned null league but rules found one — use rules
    if league is None and rules.league is not None:
        league = rules.league
        guardrail_fired = True

    # Guardrail 4: Rules found a specific event type but LLM says "news" — rules wins
    if rules.event_type != "news" and event_type == "news":
        event_type = rules.event_type
        guardrail_fired = True

    # Guardrail 4b: Reject LLM title_win when the title contains no championship evidence.
    # Prevents hallucinated title_win for fluff/embarrassment/media articles.
    if event_type == "title_win" and not _has(title_lower, *_TITLE_WIN_EVIDENCE_KW):
        event_type = rules.event_type
        guardrail_fired = True
        logger.warning(
            "Guardrail 4b: LLM title_win rejected — no championship evidence in title; fallback=%s",
            rules.event_type,
        )

    # Guardrail 5: Never downgrade importance
    if _IMPORTANCE_RANK.get(importance, 0) < _IMPORTANCE_RANK.get(rules.importance, 0):
        importance = rules.importance
        guardrail_fired = True

    # Guardrail 6: League-sport compatibility (inside merge, before entity pruning).
    # Ensures prune_sport_incompatible_entities() runs with the corrected sport.
    # normalize_league_sport_compatibility() is also called in ingestion_service for rules-only path.
    if league in _BASKETBALL_LEAGUES and sport != "basketball":
        logger.warning("Guardrail 6: %r is a basketball league → forced sport=basketball", league)
        sport = "basketball"
        guardrail_fired = True
    if league in _FOOTBALL_ONLY_LEAGUES and sport != "football":
        logger.warning("Guardrail 6: %r is a football league → forced sport=football", league)
        sport = "football"
        guardrail_fired = True

    # Guardrail 7: Source URL category hint.
    # For sources with reliable URL category schemes (e.g. Israel Hayom /sport/israeli-basketball/),
    # the pre-computed hint is treated as near-authoritative and overrides the LLM sport.
    if source_sport_hint and source_sport_hint != sport:
        logger.warning(
            "Guardrail 7: source URL category hint %r overrides LLM sport %r",
            source_sport_hint, sport,
        )
        sport = source_sport_hint
        guardrail_fired = True

    # Entities: rules entities pruned for sport compatibility, then recognized LLM entities.
    # Pruning removes basketball club entities (e.g. "Maccabi Tel Aviv Basketball") when the
    # final sport is football — the rules classifier may have added them from an ambiguous
    # "מכבי" mention before sport was resolved. Without pruning, a football article with a
    # stale basketball entity would match Guy's basketball entity topic in the relevance engine.
    pruned_rules = prune_sport_incompatible_entities(list(rules.entities), sport)
    llm_canonical = normalize_llm_entities(llm.entities, sport=sport)
    seen: set[str] = set(pruned_rules)
    entities = list(pruned_rules)
    for e in llm_canonical:
        if e not in seen:
            seen.add(e)
            entities.append(e)

    # Recompute rules-based confidence and tags from final merged fields
    new_confidence = _assign_confidence(sport, league, entities, event_type, source_id="")
    tags = _collect_tags(sport, league, entities, event_type)

    classified_by = "llm+rules_guardrail" if guardrail_fired else "llm"

    return ClassificationResult(
        sport=sport,
        league=league,
        entities=entities,
        event_type=event_type,
        importance=importance,
        confidence=new_confidence,
        tags=tags,
    ), classified_by
