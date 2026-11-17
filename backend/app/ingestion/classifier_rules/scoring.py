"""Importance, confidence and tag assignment for a classified article."""

from typing import Optional

from app.ingestion.classifier_rules.matching import _BASKETBALL_ONLY_SOURCES


# ── Importance assignment ─────────────────────────────────────────────────────

_VERY_HIGH_EVENTS = frozenset({"grand_slam_winner", "finals_result", "title_win"})
_HIGH_EVENTS = frozenset({"signing", "negotiation", "injury", "major_trade", "major_transfer"})
_HIGH_LEAGUES = frozenset({"NBA", "EuroLeague"})
_HIGH_ENTITIES = frozenset({"Maccabi Tel Aviv Basketball", "Deni Avdija"})
_LOW_EVENTS = frozenset({"schedule", "early_round_result"})


def _assign_importance(
    event_type: str,
    entities: list[str],
    league: Optional[str],
    event_certainty: str = "confirmed",
) -> str:
    if event_type in _VERY_HIGH_EVENTS:
        # very_high is reserved for confirmed championship events (issue #60):
        # a probable/weak title_win (subtitle-derived or LLM-only) is high.
        return "very_high" if event_certainty == "confirmed" else "high"

    has_high_entity = any(e in _HIGH_ENTITIES for e in entities)

    if event_type in _HIGH_EVENTS:
        if has_high_entity or league in _HIGH_LEAGUES:
            return "high"
        return "medium"

    if event_type in _LOW_EVENTS:
        return "low"

    # Generic news with no tracked entity: downgrade to low.
    # Reduces noise from generic NBA filler that has no signal keyword.
    if event_type == "news" and not has_high_entity:
        return "low"

    return "medium"


# ── Confidence assignment ─────────────────────────────────────────────────────

def _assign_confidence(
    sport: str,
    league: Optional[str],
    entities: list[str],
    event_type: str,
    source_id: str,
) -> float:
    score = 0.40
    if sport != "unknown":
        score += 0.15
    if source_id in _BASKETBALL_ONLY_SOURCES and sport == "basketball":
        score += 0.05  # source context confirms sport
    if league:
        score += 0.15
    if entities:
        score += 0.15
    if event_type != "news":
        score += 0.10
    return round(min(score, 0.95), 2)


# ── Tag collection ────────────────────────────────────────────────────────────

def _collect_tags(
    sport: str,
    league: Optional[str],
    entities: list[str],
    event_type: str,
) -> list[str]:
    tags: list[str] = []
    if sport != "unknown":
        tags.append(sport)
    if league:
        tags.append(league)
    tags.extend(entities)
    if event_type != "news":
        tags.append(event_type)
    return tags


# ── Public helper for post-classification enrichment ──────────────────────────


def compute_importance(
    event_type: str,
    entities: list[str],
    league: Optional[str],
    event_certainty: str = "confirmed",
) -> str:
    """Public wrapper for _assign_importance.

    Use when entities change after initial classification (e.g., post-LLM entity
    injection) or when the final event certainty gates very_high (#60).
    """
    return _assign_importance(event_type, entities, league, event_certainty)
