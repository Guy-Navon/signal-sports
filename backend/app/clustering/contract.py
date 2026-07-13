"""
Clustering matcher — PUBLIC INPUT/OUTPUT CONTRACT (issue #100).

This module is the integration seam between the pure matcher (#100) and
persistence/ingestion (#101). It deliberately contains NO logic and NO database
imports: #101 adapts its ORM rows into ``ClusterInput`` and persists
``ProposedCluster`` / ``MatchEdge``, without either side importing the other's
internals.

Authority: ``docs/CLUSTERING.md``. If this file and that document disagree, the
document wins.

Invariants encoded here:
- The matcher is PURE. It never touches a DB, never calls an LLM, never mutates
  its inputs, and never rewrites article facts.
- ``ClusterInput`` carries only facts the article ALREADY has. The matcher may
  not invent or infer new facts about the world.
- ``ProposedCluster`` is a GROUPING PROPOSAL, not a fact. It asserts only "these
  article ids are about one story". It carries no unioned entities, no max
  importance, no merged event facts.
- ``anchor_id`` is the basis of the stable, formation-time cluster identity that
  #101 assigns (``"cluster_" + sha1(anchor_article_id)[:16]``). The matcher picks
  the anchor deterministically; it does NOT mint the id (that is persistence's
  job, and it must not churn when members are appended later).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ClusterInput:
    """One article, reduced to exactly the facts the matcher is allowed to use.

    Every field here is an EXISTING persisted article fact. #101 builds these from
    ``ArticleRow``; tests build them from the frozen fixtures. No other article
    attribute may influence clustering.
    """
    id: str
    source: str
    title: str
    published_at: datetime
    sport: str                                  # "basketball" | "football" | "tennis" | "unknown"
    event_type: str                             # the classifier's event_type
    event_certainty: Optional[str] = None       # "confirmed" | "probable" | None
    entity_ids: tuple[str, ...] = ()            # resolved taxonomy entity ids ([] is normal!)
    primary_competition: Optional[str] = None   # comp:* id
    subtitle: str = ""


@dataclass(frozen=True)
class MatchEdge:
    """Evidence for ONE accepted pair. Persisted by #101 as ``cluster_edges``.

    Only ACCEPTED edges are represented. Rejected candidates are NOT persisted —
    near-miss diagnostics are computed on demand for QA/Debug (docs/CLUSTERING.md §4).
    """
    article_a: str
    article_b: str
    jaccard: float
    hours_apart: float
    rare_tokens: tuple[str, ...]                # the DISCRIMINATIVE shared tokens that carried it
    entity_overlap: tuple[str, ...]
    competition_overlap: tuple[str, ...]
    tier: str                                   # "A" | "B" | "C" — which gate accepted it


@dataclass(frozen=True)
class ProposedCluster:
    """A grouping proposal. NOT a fact — see module docstring.

    #101 persists this as a ``story_clusters`` row plus ``articles.cluster_id``
    membership, deriving the stable id from ``anchor_id``.
    """
    anchor_id: str                              # earliest published_at, tie -> lowest article id
    representative_id: str                      # the §9.1 ladder winner (corpus-level, user-independent)
    member_ids: tuple[str, ...]                 # includes the anchor; sorted for determinism
    event_state: str                            # the single event_type ALL members share (grouping key)
    sport: Optional[str]                        # grouping key only; None when members were unknown-sport
    edges: tuple[MatchEdge, ...] = field(default_factory=tuple)

    @property
    def size(self) -> int:
        return len(self.member_ids)


@dataclass(frozen=True)
class RejectionReason:
    """Bounded, on-demand near-miss diagnostic. NEVER persisted (docs/CLUSTERING.md §4)."""
    article_a: str
    article_b: str
    reason: str          # see matcher.Rejection.* constants
    detail: str = ""
