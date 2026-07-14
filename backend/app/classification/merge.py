"""
Merge LLM classification result with deterministic rules result.

Strategy: LLM primary. Rules fire only as guardrails for known failure modes.
Entities from rules are canonical (required for relevance engine string matching);
LLM entities go through the normalization map and any recognized ones are appended.
"""

import logging
from typing import Optional

from app.classification.entity_normalizer import normalize_llm_entities, prune_sport_incompatible_entities
from app.classification.event_evidence import validate_event_evidence
from app.classification.llm_result import LLMClassificationResult
from app.ingestion.classifier import ClassificationResult, _assign_confidence, _collect_tags
from app.classification.sport_guards import committed_sport, is_unsupported_sport

logger = logging.getLogger(__name__)

_IMPORTANCE_RANK = {"very_high": 4, "high": 3, "medium": 2, "low": 1}

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
        event_certainty=result.event_certainty,
    )


def merge_with_guardrails(
    llm: LLMClassificationResult,
    rules: ClassificationResult,
    title_lower: str,
    football_maccabi_detected: bool = False,
    source_sport_hint: Optional[str] = None,
    subtitle_lower: Optional[str] = None,
) -> tuple[ClassificationResult, str]:
    """
    Returns (final ClassificationResult, classified_by string).
    LLM wins on all fields except where guardrails fire.
    """
    sport = llm.sport
    league = llm.league
    event_type = llm.event_type
    importance = llm.importance
    event_certainty = "weak" if event_type != "news" else "confirmed"
    guardrail_fired = False
    evidence_text = title_lower
    if subtitle_lower:
        evidence_text = f"{title_lower} {subtitle_lower}"

    # Guardrail 0 (issue #113): UNSUPPORTED DOMAIN → ABSTAIN.
    # The taxonomy models basketball, football and tennis. It does not model MMA/UFC/boxing.
    # Faced with a UFC report the LLM invented "football" (its own reason literally read
    # "Football match result between Conor McGregor and Max Holloway in UFC"), and two
    # sources then disagreed on the same fight. For a sport we do not model, the honest
    # answer is "unknown" — abstention beats a wrong fact, and a wrong sport propagates all
    # the way into visibility, preference matching and push. Runs FIRST: nothing downstream
    # should get the chance to assert a sport we cannot support.
    if is_unsupported_sport(evidence_text):
        if sport != "unknown":
            logger.warning(
                "Guardrail 0: unsupported domain (MMA/UFC/boxing) — abstaining from sport %r",
                sport,
            )
            guardrail_fired = True
        sport = "unknown"
        league = None

    # Guardrail 1: Football Maccabi clubs (deterministic, high precision)
    # Rules detected an explicit football Maccabi club keyword — LLM must not override.
    elif football_maccabi_detected and sport != "football":
        sport = "football"
        league = rules.league
        guardrail_fired = True
        logger.debug("Guardrail 1 fired: football Maccabi detected, overriding LLM sport")

    # Guardrail 1b (issue #113): COMMITTED SPORT VOCABULARY beats a contradicting LLM sport.
    #
    # "Deterministic evidence first" was NOT actually enforced for sport: guardrail 2 below
    # only overrides the LLM when the LLM says *unknown*. If the rules resolved a sport and
    # the LLM disagreed, the LLM silently won. That is how an article whose subtitle reads
    # "נבחרת העתודה … נבחרה לחמישיית הטורניר" (unmistakably basketball) was classified
    # FOOTBALL — and why two sources reported the same story with contradictory sports.
    #
    # Only UNAMBIGUOUS, single-sport vocabulary qualifies (see sport_guards.py). When both
    # sports' vocabulary is present, committed_sport() returns None and we leave the
    # decision alone — that is real ambiguity, and abstention beats picking a side.
    if sport != "unknown":
        proven = committed_sport(evidence_text)
        if proven is not None and proven != sport:
            logger.warning(
                "Guardrail 1b: committed %s vocabulary overrides LLM sport %r",
                proven, sport,
            )
            sport = proven
            league = rules.league if rules.sport == proven else None
            guardrail_fired = True

    # Guardrail 2: LLM says sport=unknown but rules found a sport — use rules
    if sport == "unknown" and rules.sport != "unknown" and not is_unsupported_sport(evidence_text):
        sport = rules.sport
        guardrail_fired = True

    # Guardrail 3: LLM returned null league but rules found one — use rules
    if league is None and rules.league is not None:
        league = rules.league
        guardrail_fired = True

    # Guardrail 4: Rules found a specific event type but LLM says "news" — rules wins
    if rules.event_type != "news" and event_type == "news":
        event_type = rules.event_type
        event_certainty = rules.event_certainty
        guardrail_fired = True

    # Guardrail 4b generalized: every specific event type needs semantic evidence.
    evidence = validate_event_evidence(event_type, evidence_text, source="llm", sport=sport)
    if event_type != "news" and not evidence.valid:
        fallback = rules.event_type if rules.event_type != event_type else "news"
        fallback_evidence = validate_event_evidence(
            fallback, evidence_text, source="rules", sport=sport
        )
        event_type = fallback if fallback_evidence.valid else "news"
        event_certainty = fallback_evidence.certainty if fallback_evidence.valid else "confirmed"
        guardrail_fired = True
        logger.warning(
            "Guardrail 4b: LLM event_type %s rejected — missing semantic evidence; fallback=%s",
            llm.event_type, event_type,
        )
    elif event_type != "news":
        event_certainty = (
            "confirmed"
            if event_type == rules.event_type and rules.event_type != "news"
            else evidence.certainty
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
    # NOTE (#113): a source hint must never resurrect a sport for an UNSUPPORTED domain.
    # A UFC report filed under a section hint is still not a sport we model.
    # A hint FILLS a gap; it never overrides committed contradictory evidence (#113).
    _committed_here = committed_sport(evidence_text)
    if (
        source_sport_hint
        and source_sport_hint != sport
        and not is_unsupported_sport(evidence_text)
        and not (_committed_here is not None and _committed_here != source_sport_hint)
    ):
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
        event_certainty=event_certainty,
    ), classified_by
