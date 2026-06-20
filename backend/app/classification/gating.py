"""
Selective LLM gating — per-article decision on whether to call the LLM.

Pure function; no I/O, no side effects. All inputs are passed explicitly.
Called only for articles already eligible for LLM (Hebrew broad source,
provider active, circuit not open). Non-eligible articles never touch this module.

Environment variable CLASSIFICATION_LLM_GATING (default: enabled):
  enabled  — skip LLM when deterministic result is already strong (recommended)
  disabled — always call LLM; reproduces pre-gating behaviour for benchmarking

Changing this variable requires a backend restart (evaluated once at import time).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from app.ingestion.classifier import ClassificationResult

_GATING_ENABLED: bool = os.getenv("CLASSIFICATION_LLM_GATING", "enabled").lower() == "enabled"

# League keywords that appear unambiguously in article text and are supported by
# the classifier's ALLOWED_LEAGUES. WNCA/NCAA excluded — not in ALLOWED_LEAGUES.
_CLEAR_LEAGUE_KEYWORDS: tuple[str, ...] = (
    "nba",
    "יורוליג",       # EuroLeague (Hebrew)
    "euroleague",
    "יורוקאפ",       # EuroCup (Hebrew)
    "eurocup",
    "euro cup",
    "acb",            # Spanish ACB
    "bsl",            # Turkish BSL
    "greek basket league",
    "lba",            # Italian LBA
    "lnb",            # French LNB
    "ליגת winner",    # Israeli Basketball League colloquial Hebrew names
    "ליגת וינר",
)


@dataclass(frozen=True)
class LLMGateDecision:
    should_call_llm: bool
    reason: str


def should_call_llm_for_article(
    *,
    source_id: str,
    title: str,
    subtitle: Optional[str],
    rules_result: ClassificationResult,
    source_sport_hint: Optional[str],
) -> LLMGateDecision:
    """Return whether to call the LLM for this article, with an explainable reason.

    Only called for articles already eligible for LLM (Hebrew broad source,
    provider active, circuit not open). Non-eligible articles are not gated here.

    Skip reasons mean: "eligible, but deterministic result is strong enough."
    Call reasons mean: "eligible, and LLM is likely to add value."
    """
    if not _GATING_ENABLED:
        return LLMGateDecision(should_call_llm=True, reason="gating_disabled")

    sport = rules_result.sport
    conf = rules_result.confidence
    tags = rules_result.tags
    league = rules_result.league
    entities = rules_result.entities
    event_type = rules_result.event_type

    # ── Force-call conditions (take precedence over every skip condition) ─────────
    # ambiguous_club checked first: more specific reason than sport_unknown when both apply,
    # since the classifier produces sport=unknown alongside ambiguous_club in practice.

    if "ambiguous_club" in tags:
        return LLMGateDecision(should_call_llm=True, reason="ambiguous_club")

    if sport == "unknown":
        return LLMGateDecision(should_call_llm=True, reason="sport_unknown")

    if conf < 0.55:
        return LLMGateDecision(should_call_llm=True, reason="low_rules_confidence")

    # ── Skip conditions (evaluated in order of decreasing certainty) ─────────────
    #
    # Each condition requires sport != unknown and no ambiguous_club (already
    # guaranteed by the force-call checks above, but stated in each condition
    # for clarity).

    combined_lower = (title + " " + (subtitle or "")).lower()

    # 1. Clear league keyword in title/subtitle AND classifier resolved the same league.
    #    Requires: keyword hit + league resolved + sport known + conf >= 0.65.
    #    The keyword check is an additional confirming signal; the primary gate is
    #    that the deterministic classifier already produced a concrete league value.
    if (
        league is not None
        and conf >= 0.65
        and any(kw in combined_lower for kw in _CLEAR_LEAGUE_KEYWORDS)
    ):
        return LLMGateDecision(should_call_llm=False, reason="clear_league_in_title")

    # 2. Strong source URL hint that agrees with deterministic sport AND result
    #    is already useful (has league, entity, or specific event type).
    #    Rationale: the hint confirms sport, but LLM may still add league/entity/event
    #    context. Only skip if at least one of those is already resolved.
    if source_sport_hint is not None and source_sport_hint == sport and conf >= 0.65:
        has_extra_context = (
            league is not None
            or bool(entities)
            or event_type != "news"
        )
        if has_extra_context:
            return LLMGateDecision(should_call_llm=False, reason="strong_source_sport_hint")
        else:
            return LLMGateDecision(
                should_call_llm=True, reason="source_hint_only_missing_context"
            )

    # 3. Strong deterministic result: sport + league + high confidence.
    if league is not None and conf >= 0.80:
        return LLMGateDecision(should_call_llm=False, reason="strong_deterministic_result")

    # 4. Known entity + sport + specific (non-news) event type + good confidence.
    if entities and event_type != "news" and conf >= 0.75:
        return LLMGateDecision(should_call_llm=False, reason="known_entity_compatible")

    # ── Default: call LLM ─────────────────────────────────────────────────────────
    return LLMGateDecision(should_call_llm=True, reason="hebrew_broad_source_unclear")
