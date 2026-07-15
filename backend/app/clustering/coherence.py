"""
Grouping + cluster-coherence validation (issue #100) — docs/CLUSTERING.md §7.4, §9.1.

PLAIN UNION-FIND IS NOT SUFFICIENT, and this module exists to say why.

Connected components will happily merge a weak chain:

    A ~ B   "Maccabi TLV signs the American guard Johnson"
    B ~ C   "Maccabi TLV and Hapoel TLV both sign American guards"   <-- the bridge
            "Hapoel TLV signs the American guard Williams"

A and C are DIFFERENT SIGNINGS AT DIFFERENT CLUBS. Union-find puts all three in one
cluster because B touches both. The coherence rules below break that chain:

  - an initial accepted PAIR may form a cluster;
  - a LATE MEMBER must match the current REPRESENTATIVE, or at least
    ``min_member_matches_to_join`` existing members — one weak edge is not enough;
  - the cluster must stay GLOBALLY compatible: one event_state, compatible sport,
    total span within ``max_cluster_time_span_hours``;
  - validation runs AFTER candidate grouping, so chains formed during batch
    processing are broken up rather than silently accepted.

When in doubt: abstain.
"""

from collections import defaultdict
from typing import Optional

from app.clustering.config import ClusteringConfig
from app.clustering.contract import ClusterInput, MatchEdge, ProposedCluster
from app.clustering.event_states import hours_apart
from app.clustering.intra_source import TIER_INTRA_SOURCE
from app.clustering.matcher import sports_hard_reject


# ── Representative selection (docs/CLUSTERING.md §9.1) ────────────────────────
# Deterministic ladder, NO SOURCE RANKING (source quality is a separate future
# contract, deliberately out of v1):
#   1. fact completeness   2. event certainty   3. recency   4. stable article id
#
# Lives here rather than in persistence because COHERENCE NEEDS IT: the
# "match the representative" rule cannot be evaluated without it. #101 imports this
# function rather than re-implementing the ladder.

_CERTAINTY_RANK = {"confirmed": 2, "probable": 1}


def _fact_completeness(a: ClusterInput) -> int:
    score = 0
    if a.entity_ids:
        score += 1
    if a.primary_competition:
        score += 1
    if a.event_type and a.event_type != "news":
        score += 1
    return score


def _representative_key(a: ClusterInput):
    # Sort DESC on the first three, ASC on id → negate id via reversed comparison
    # by returning id last and sorting with a stable tuple.
    return (
        _fact_completeness(a),
        _CERTAINTY_RANK.get(a.event_certainty or "", 0),
        a.published_at,
    )


def select_representative(members: list[ClusterInput]) -> ClusterInput:
    """The corpus-level representative — global, user-independent."""
    best = max(
        members,
        key=lambda a: (
            _fact_completeness(a),
            _CERTAINTY_RANK.get(a.event_certainty or "", 0),
            a.published_at.timestamp(),
            # invert id so that on a full tie the LOWEST id wins deterministically
            tuple(-ord(c) for c in a.id),
        ),
    )
    return best


def select_anchor(members: list[ClusterInput]) -> ClusterInput:
    """Founding member: earliest published_at, tie -> lowest article id.

    The basis of the stable formation-time cluster id (#101). Deliberately NOT the
    representative: the representative may change as better articles arrive, but the
    anchor — and therefore the id — must not.
    """
    return min(members, key=lambda a: (a.published_at, a.id))


# ── Grouping ─────────────────────────────────────────────────────────────────

def _connected_components(
    ids: list[str], edges: list[MatchEdge]
) -> list[list[str]]:
    parent = {i: i for i in ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        ra, rb = find(e.article_a), find(e.article_b)
        if ra != rb:
            parent[ra] = rb

    groups: dict[str, list[str]] = defaultdict(list)
    for i in ids:
        groups[find(i)].append(i)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def _cluster_globally_compatible(
    members: list[ClusterInput],
    cfg: ClusteringConfig,
    intra_pairs: frozenset[frozenset] = frozenset(),
) -> bool:
    """One event_state, source uniqueness (unless PROVEN republish), no cross-sport
    pair, bounded time span.

    SOURCE UNIQUENESS is a CLUSTER invariant, not merely a pair gate. The cross-source
    pair rule alone does NOT prevent two articles from the same source ending up in one
    cluster: A(src X) ~ B(src Y) and C(src X) ~ B(src Y) are both legal pairs, yet
    union-find would put A, B and C together — quietly re-introducing the same-source
    chaining that v1 declares a non-goal. Enforcing it here means no transitive path can
    bypass it.

    #123 REVISION, deliberately narrow: a same-source pair is admissible IFF that exact
    pair carries a tier-I intra-source edge — the near-republish proven under the
    stricter dedicated contract (intra_source.py). ``intra_pairs`` holds those proven
    pairs as id-frozensets. Same-source co-membership by TRANSITIVITY remains banned:
    two same-source articles that were never directly proven to be republishes of each
    other cannot share a cluster, no matter what connects them.
    """
    if len({m.event_type for m in members}) != 1:
        return False

    for i, a in enumerate(members):
        for b in members[i + 1:]:
            if a.source == b.source and frozenset((a.id, b.id)) not in intra_pairs:
                return False

    for i, a in enumerate(members):
        for b in members[i + 1:]:
            if sports_hard_reject(a, b):
                return False
    times = [m.published_at for m in members]
    span = hours_apart(max(times), min(times))
    return span <= cfg.max_cluster_time_span_hours


def validate_coherence(
    component: list[ClusterInput],
    edges: list[MatchEdge],
    cfg: ClusteringConfig,
) -> Optional[list[ClusterInput]]:
    """Rebuild a candidate component into a COHERENT cluster, or abstain.

    Greedy, deterministic, precision-first:
      - seed from the earliest accepted pair;
      - consider remaining members in publication order;
      - admit one only if it matches the CURRENT representative, or at least
        ``min_member_matches_to_join`` current members;
      - re-check global compatibility after every admission;
      - a member that cannot justify itself is LEFT OUT (it may still cluster with
        others on a later pass, or abstain entirely).

    Returns the coherent member list (>= 2), or None if nothing coherent survives.
    """
    by_id = {a.id: a for a in component}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e.article_a in by_id and e.article_b in by_id:
            adjacency[e.article_a].add(e.article_b)
            adjacency[e.article_b].add(e.article_a)

    # Pairs proven under the intra-source republish contract (#123) — the ONLY
    # legal form of same-source co-membership.
    intra_pairs = frozenset(
        frozenset((e.article_a, e.article_b))
        for e in edges
        if e.tier == TIER_INTRA_SOURCE
        and e.article_a in by_id and e.article_b in by_id
    )

    # Seed: the edge whose endpoints are earliest — deterministic and stable.
    seed_edge = min(
        (e for e in edges if e.article_a in by_id and e.article_b in by_id),
        key=lambda e: (
            min(by_id[e.article_a].published_at, by_id[e.article_b].published_at),
            sorted((e.article_a, e.article_b)),
        ),
        default=None,
    )
    if seed_edge is None:
        return None

    members = [by_id[seed_edge.article_a], by_id[seed_edge.article_b]]
    if not _cluster_globally_compatible(members, cfg, intra_pairs):
        return None

    remaining = sorted(
        (a for a in component if a.id not in {m.id for m in members}),
        key=lambda a: (a.published_at, a.id),
    )

    for cand in remaining:
        if len(members) >= cfg.max_cluster_size:
            # Suspicious-merge guard: stop admitting rather than silently growing.
            break

        # ONE MEMBER PER SOURCE (v1 invariant, #123-revised). If this source is already
        # represented, the candidate is admissible ONLY when it carries a proven tier-I
        # republish edge to EVERY same-source incumbent — otherwise it is rejected FROM
        # THIS CLUSTER and left unclustered. We do NOT automatically evict the
        # incumbent: the incumbent got here on earlier, at least as strong evidence,
        # and silently swapping members would make the cluster's composition depend on
        # arrival order. Deterministic by publication order.
        same_source_incumbents = [m for m in members if m.source == cand.source]
        if any(
            frozenset((cand.id, m.id)) not in intra_pairs
            for m in same_source_incumbents
        ):
            continue

        member_ids = {m.id for m in members}
        matches = adjacency[cand.id] & member_ids
        anchor = select_anchor(members)

        # THE anti-transitive-chaining rule: a member that touches only ONE PERIPHERAL
        # member cannot drag its own neighbours in. It must connect to the structurally
        # CENTRAL member (the anchor), or corroborate itself against at least
        # ``min_member_matches_to_join`` existing members.
        #
        # CONTRACT CORRECTION (#100). docs/CLUSTERING.md originally said "match the
        # current REPRESENTATIVE or >= 2 members". That is unsafe. The representative is
        # a DISPLAY concept chosen by FACT COMPLETENESS — and a bridge article is
        # typically the *richest* one (it names both clubs / both players), so it tends
        # to WIN the representative ladder. "Match the representative" would then be
        # satisfied by matching the bridge itself — admitting exactly the transitive
        # chain the rule exists to block. A test constructed for this reproduced it.
        #
        # Coherence needs a STRUCTURAL notion of centrality, not a factual one. The
        # ANCHOR is that: earliest, part of the seed pair, chosen by publication order.
        # A bridge (later, derivative) cannot become the anchor. Keying on the anchor
        # blocks the chain AND admits the genuine 4th Recanati source, whose short
        # headline matches the anchor strongly but falls just under the jaccard floor
        # against the two longer articles.
        joins = (
            anchor.id in matches
            or len(matches) >= cfg.min_member_matches_to_join
        )
        if not joins:
            continue

        trial = members + [cand]
        if not _cluster_globally_compatible(trial, cfg, intra_pairs):
            continue
        members = trial

    if len(members) < 2:
        return None
    return members


def build_clusters(
    articles: list[ClusterInput],
    edges: list[MatchEdge],
    cfg: ClusteringConfig,
) -> list[ProposedCluster]:
    """Candidate grouping, then FINAL coherence validation (never union-find alone)."""
    by_id = {a.id: a for a in articles}
    components = _connected_components([a.id for a in articles], edges)

    proposals: list[ProposedCluster] = []
    for comp_ids in components:
        comp = [by_id[i] for i in comp_ids]
        comp_edges = [
            e for e in edges
            if e.article_a in set(comp_ids) and e.article_b in set(comp_ids)
        ]
        coherent = validate_coherence(comp, comp_edges, cfg)
        if coherent is None:
            continue

        member_ids = {m.id for m in coherent}
        kept_edges = tuple(
            e for e in comp_edges
            if e.article_a in member_ids and e.article_b in member_ids
        )
        anchor = select_anchor(coherent)
        rep = select_representative(coherent)
        sports = {m.sport for m in coherent if m.sport != "unknown"}

        proposals.append(ProposedCluster(
            anchor_id=anchor.id,
            representative_id=rep.id,
            member_ids=tuple(sorted(member_ids)),
            event_state=coherent[0].event_type,
            sport=next(iter(sports)) if len(sports) == 1 else None,
            edges=kept_edges,
        ))

    proposals.sort(key=lambda p: p.anchor_id)
    return proposals
