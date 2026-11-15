"""Results provider protocol (issue #178).

A provider fetches games for a set of competition ids and returns fully
NORMALIZED games plus a per-competition error map. Normalization (including
taxonomy team resolution) happens inside the provider so nothing downstream —
repository, service, API — ever sees provider field names. Partial failure is
first-class: one competition erroring must not lose the others.

A provider may also offer per-game detail for finished games through the
optional ``fetch_details`` (``DetailProvider``, issue #517).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from app.results.models import NormalizedGame, NormalizedGameDetail


@dataclass
class FetchOutcome:
    games: list[NormalizedGame] = field(default_factory=list)
    # competition_id -> human error string (empty = all fetches succeeded)
    errors: dict[str, str] = field(default_factory=dict)
    # competition_id -> count fetched (observability)
    fetched_counts: dict[str, int] = field(default_factory=dict)
    # Competitions not fetched because the provider rate-limited us (429). They
    # did not fail on their own; the sync stopped sending requests.
    not_checked: list[str] = field(default_factory=list)
    # The provider's Retry-After when a 429 stopped the fetch; None otherwise.
    retry_after_seconds: Optional[float] = None


class ResultsProvider(Protocol):
    name: str

    def fetch(self, competition_ids: list[str]) -> FetchOutcome:
        """Fetch and normalize recent games for the given competitions."""
        ...


# ── Optional detail capability (issue #517) ───────────────────────────────────

@dataclass
class DetailOutcome:
    """What ``fetch_details`` returns. Partial failure is first-class, as in
    ``FetchOutcome``: one game erroring must not lose the others.

    A requested game that is in none of ``details``, ``errors`` or
    ``not_checked`` simply has no detail yet (for example, the box score is not
    published); it stays a candidate for a later run.
    """
    details: list[NormalizedGameDetail] = field(default_factory=list)
    # game id -> short error string (no URLs or keys: it is stored and served)
    errors: dict[str, str] = field(default_factory=dict)
    # Game ids not requested because the provider rate-limited us (429).
    not_checked: list[str] = field(default_factory=list)
    # The provider's Retry-After when a 429 stopped the fetch; None otherwise.
    retry_after_seconds: Optional[float] = None


class DetailProvider(Protocol):
    """A provider that can also return per-game detail. Optional: providers
    without detail (TheSportsDB) just don't define ``fetch_details``."""
    name: str

    def fetch_details(self, games: list[NormalizedGame]) -> DetailOutcome:
        """Fetch detail for these finished games, all of them this provider's
        own (same ``provider`` name). Pace requests like ``fetch`` does."""
        ...


def supports_details(provider: object) -> bool:
    return callable(getattr(provider, "fetch_details", None))
