"""
Deterministic story clustering (Milestone 5).

Authority: ``docs/CLUSTERING.md``. Code that disagrees with that document is a bug.

Public surface — everything #101 (persistence/ingestion) is allowed to import:

    cluster_articles(articles, cfg) -> ClusteringResult      # the entry point
    ClusterInput, ProposedCluster, MatchEdge, RejectionReason  # the I/O contract
    ClusteringConfig, DEFAULT_CONFIG                          # the tunables
    select_representative, select_anchor                      # the §9.1 ladder

Nothing here touches a database, an LLM, an embedding, or the network. The matcher
is a pure function of the article facts it is handed.
"""

from app.clustering.coherence import select_anchor, select_representative
from app.clustering.config import DEFAULT_CONFIG, ClusteringConfig
from app.clustering.contract import (
    ClusterInput,
    MatchEdge,
    ProposedCluster,
    RejectionReason,
)
from app.clustering.service import ClusteringResult, cluster_articles

__all__ = [
    "cluster_articles",
    "ClusteringResult",
    "ClusterInput",
    "ProposedCluster",
    "MatchEdge",
    "RejectionReason",
    "ClusteringConfig",
    "DEFAULT_CONFIG",
    "select_representative",
    "select_anchor",
]
