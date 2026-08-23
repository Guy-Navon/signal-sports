"""Normalized game status vocabulary + provider-string mapping (issue #178)."""
from __future__ import annotations

from typing import Optional

# The project-owned status vocabulary. Providers map INTO this set.
SCHEDULED = "scheduled"
LIVE = "live"
FINAL = "final"
POSTPONED = "postponed"
CANCELLED = "cancelled"
UNKNOWN = "unknown"

STATUSES = (SCHEDULED, LIVE, FINAL, POSTPONED, CANCELLED, UNKNOWN)

# Statuses that represent a completed game whose score is meaningful.
COMPLETED = frozenset({FINAL})

# TheSportsDB `strStatus` tokens seen across basketball feeds.
_FINAL_TOKENS = {"ft", "aot", "aet", "match finished", "finished", "final", "fin"}
_LIVE_TOKENS = {
    "1h", "2h", "ht", "live", "in play", "q1", "q2", "q3", "q4",
    "ot", "1q", "2q", "3q", "4q", "playing",
}
_SCHEDULED_TOKENS = {"ns", "not started", "sched", "scheduled", "tbd", "pst-tbd"}
_POSTPONED_TOKENS = {"pp", "postp", "postponed", "susp", "suspended", "abd", "abandoned"}
_CANCELLED_TOKENS = {"canc", "cancelled", "canceled", "awarded", "wo", "walkover"}


def parse_status(
    raw_status: Optional[str],
    *,
    postponed_flag: Optional[str] = None,
    has_score: bool,
    starts_in_future: bool,
) -> str:
    """Map a provider status string to the normalized vocabulary.

    Falls back to structural evidence when the string is missing/unknown: a
    game with a score is FINAL; a future-dated game with no score is SCHEDULED.
    """
    if postponed_flag and postponed_flag.strip().lower() in {"yes", "true", "1"}:
        return POSTPONED

    token = (raw_status or "").strip().lower()
    if token in _FINAL_TOKENS:
        return FINAL
    if token in _LIVE_TOKENS:
        return LIVE
    if token in _POSTPONED_TOKENS:
        return POSTPONED
    if token in _CANCELLED_TOKENS:
        return CANCELLED
    if token in _SCHEDULED_TOKENS:
        return SCHEDULED

    # Unknown / empty token → infer from structure.
    if has_score and not starts_in_future:
        return FINAL
    if starts_in_future and not has_score:
        return SCHEDULED
    if has_score:
        return FINAL
    return UNKNOWN


def winner(status: str, home_score: Optional[int], away_score: Optional[int]) -> Optional[str]:
    """"home" | "away" | "draw" for completed games with scores, else None."""
    if status not in COMPLETED or home_score is None or away_score is None:
        return None
    if home_score > away_score:
        return "home"
    if away_score > home_score:
        return "away"
    return "draw"
