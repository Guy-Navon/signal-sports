"""
Clustering matcher — the single public entry point (issue #100).

    cluster_articles(articles, cfg) -> ClusteringResult

PURE. No DB, no LLM, no network, no mutation of inputs. #101 (persistence /
ingestion) calls this and persists the result; it never reaches into the internals.

The article list passed in IS the candidate lookback window: document frequencies —
and therefore what counts as "discriminative" — are computed relative to it, never
against a frozen global corpus (docs/CLUSTERING.md §7.3).
"""

from dataclasses import dataclass, field
from itertools import combinations

from app.clustering.coherence import build_clusters
from app.clustering.config import DEFAULT_CONFIG, ClusteringConfig
from app.clustering.contract import (
    ClusterInput,
    MatchEdge,
    ProposedCluster,
    RejectionReason,
)
from app.clustering.event_states import is_clusterable_state, is_in_play
from app.clustering.intra_source import intra_source_match
from app.clustering.matcher import match_pair
from app.clustering.tokens import DocumentFrequency, tokenize


@dataclass
class ClusteringResult:
    clusters: list[ProposedCluster] = field(default_factory=list)
    edges: list[MatchEdge] = field(default_factory=list)
    # Bounded, on-demand near-miss diagnostics for QA/Debug. NEVER persisted (§4).
    rejections: list[RejectionReason] = field(default_factory=list)
    # Articles excluded from candidacy entirely (in-play, non-clusterable state).
    excluded_ids: list[str] = field(default_factory=list)

    @property
    def clustered_article_ids(self) -> set[str]:
        return {mid for c in self.clusters for mid in c.member_ids}


def _eligible(a: ClusterInput) -> bool:
    """Candidacy filter: in-play snapshots and non-clusterable states never compete."""
    if not is_clusterable_state(a.event_type):
        return False
    if is_in_play(a.title, a.subtitle):
        return False
    return True


def cluster_articles(
    articles: list[ClusterInput],
    cfg: ClusteringConfig = DEFAULT_CONFIG,
    collect_rejections: bool = False,
) -> ClusteringResult:
    """Group articles that report the same real-world story.

    Args:
        articles: the candidate lookback window. DF is relative to THIS list.
        cfg: tunable thresholds. Changing them requires re-running the #102 gate.
        collect_rejections: gather near-miss diagnostics (QA/Debug only — these are
            computed on demand and are never persisted).
    """
    result = ClusteringResult()

    eligible = [a for a in articles if _eligible(a)]
    result.excluded_ids = sorted(
        {a.id for a in articles} - {a.id for a in eligible}
    )
    if len(eligible) < 2:
        return result

    tokens = {a.id: tokenize(f"{a.title} {a.subtitle}".strip()) for a in eligible}
    title_tokens = {a.id: tokenize(a.title) for a in eligible}
    df = DocumentFrequency.over(tokens[a.id] for a in eligible)

    for a, b in combinations(eligible, 2):
        if a.source == b.source:
            # Same-source pairs never reach the cross-source matcher (its hard
            # gate is untouched); they are evaluated under the much stricter
            # intra-source near-republish contract (#123) instead.
            edge, rejection = intra_source_match(
                a, b, title_tokens[a.id], title_tokens[b.id],
                tokens[a.id], tokens[b.id], df, cfg,
            )
        else:
            edge, rejection = match_pair(a, b, tokens[a.id], tokens[b.id], df, cfg)
        if edge is not None:
            result.edges.append(edge)
        elif collect_rejections and rejection is not None:
            result.rejections.append(rejection)

    result.clusters = build_clusters(eligible, result.edges, cfg)

    # Keep only edges that survived coherence validation — a rejected transitive
    # bridge must not leave a dangling "accepted" edge behind.
    kept = {(e.article_a, e.article_b) for c in result.clusters for e in c.edges}
    result.edges = [e for e in result.edges if (e.article_a, e.article_b) in kept]

    return result
