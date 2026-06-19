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
from app.ingestion.classifier import ClassificationResult, _assign_confidence, _collect_tags

logger = logging.getLogger(__name__)

_IMPORTANCE_RANK = {"very_high": 4, "high": 3, "medium": 2, "low": 1}


def merge_with_guardrails(
    llm: LLMClassificationResult,
    rules: ClassificationResult,
    title_lower: str,
    football_maccabi_detected: bool = False,
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

    # Guardrail 5: Never downgrade importance
    if _IMPORTANCE_RANK.get(importance, 0) < _IMPORTANCE_RANK.get(rules.importance, 0):
        importance = rules.importance
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
