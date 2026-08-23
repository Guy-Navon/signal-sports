"""Results provider protocol (issue #178).

A provider fetches games for a set of competition ids and returns fully
NORMALIZED games plus a per-competition error map. Normalization (including
taxonomy team resolution) happens inside the provider so nothing downstream —
repository, service, API — ever sees provider field names. Partial failure is
first-class: one competition erroring must not lose the others.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.results.models import NormalizedGame


@dataclass
class FetchOutcome:
    games: list[NormalizedGame] = field(default_factory=list)
    # competition_id -> human error string (empty = all fetches succeeded)
    errors: dict[str, str] = field(default_factory=dict)
    # competition_id -> count fetched (observability)
    fetched_counts: dict[str, int] = field(default_factory=dict)


class ResultsProvider(Protocol):
    name: str

    def fetch(self, competition_ids: list[str]) -> FetchOutcome:
        """Fetch and normalize recent games for the given competitions."""
        ...
