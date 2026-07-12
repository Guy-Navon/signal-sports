"""
Cluster persistence (issue #101) — docs/CLUSTERING.md §4, §8.

The persistence half of clustering. It consumes the pure matcher's output
(``ProposedCluster`` / ``MatchEdge`` from ``app.clustering.contract``) and writes it,
without either side importing the other's internals.

Three invariants this module exists to guarantee:

  1. **Repeated clustering creates no duplicate clusters.**
  2. **Repeated clustering churns no existing ids.**
  3. **Late arrivals append to the existing cluster atomically.**

And two it must never violate:

  - **Article facts are never rewritten.** The ONLY column this module touches on
    ``articles`` is ``cluster_id`` — membership, not facts.
  - **No cluster-level authoritative facts.** ``event_state``/``sport`` on the cluster
    row are grouping keys (what the members had in common), not assertions.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.clustering.contract import MatchEdge, ProposedCluster
from app.clustering.identity import cluster_id_from_anchor, edge_id
from app.db.orm_models import ArticleRow, ClusterEdgeRow, StoryClusterRow


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ── Reads ────────────────────────────────────────────────────────────────────

def get_cluster(session: Session, cluster_id: str) -> Optional[StoryClusterRow]:
    return session.get(StoryClusterRow, cluster_id)


def get_all_clusters(session: Session) -> list[StoryClusterRow]:
    return session.query(StoryClusterRow).order_by(StoryClusterRow.id).all()


def get_members(session: Session, cluster_id: str) -> list[ArticleRow]:
    return (
        session.query(ArticleRow)
        .filter(ArticleRow.cluster_id == cluster_id)
        .order_by(ArticleRow.id)
        .all()
    )


def get_member_ids(session: Session, cluster_id: str) -> list[str]:
    rows = (
        session.query(ArticleRow.id)
        .filter(ArticleRow.cluster_id == cluster_id)
        .order_by(ArticleRow.id)
        .all()
    )
    return [r[0] for r in rows]


def get_edges(session: Session, cluster_id: str) -> list[ClusterEdgeRow]:
    return (
        session.query(ClusterEdgeRow)
        .filter(ClusterEdgeRow.cluster_id == cluster_id)
        .order_by(ClusterEdgeRow.id)
        .all()
    )


def find_cluster_by_anchor(session: Session, anchor_article_id: str) -> Optional[StoryClusterRow]:
    return session.get(StoryClusterRow, cluster_id_from_anchor(anchor_article_id))


def find_existing_cluster_for_members(
    session: Session, member_ids: list[str]
) -> Optional[StoryClusterRow]:
    """Reconcile a recomputed group to an existing cluster by MAXIMUM MEMBER OVERLAP.

    This is what makes recomputation idempotent WITHOUT churning ids (§8): a recomputed
    group that mostly matches an existing cluster IS that cluster, even if its anchor
    changed or a member came and went. Only a genuinely new group mints a new id.
    """
    if not member_ids:
        return None
    rows = (
        session.query(ArticleRow.cluster_id)
        .filter(ArticleRow.id.in_(member_ids), ArticleRow.cluster_id.isnot(None))
        .all()
    )
    counts: dict[str, int] = {}
    for (cid,) in rows:
        counts[cid] = counts.get(cid, 0) + 1
    if not counts:
        return None
    # Highest overlap wins; ties broken by id for determinism.
    best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return session.get(StoryClusterRow, best)


# ── Writes ───────────────────────────────────────────────────────────────────

def _write_edges(session: Session, cluster_id: str, edges: tuple[MatchEdge, ...]) -> None:
    """Upsert accepted evidence. Edge ids are order-independent, so re-running cannot
    duplicate a row for the same undirected pair."""
    for e in edges:
        eid = edge_id(cluster_id, e.article_a, e.article_b)
        row = session.get(ClusterEdgeRow, eid)
        if row is None:
            row = ClusterEdgeRow(id=eid, cluster_id=cluster_id)
            session.add(row)
        row.article_a = e.article_a
        row.article_b = e.article_b
        row.jaccard = e.jaccard
        row.hours_apart = e.hours_apart
        row.rare_tokens = list(e.rare_tokens)
        row.entity_overlap = list(e.entity_overlap)
        row.competition_overlap = list(e.competition_overlap)
        row.tier = e.tier


def persist_cluster(
    session: Session,
    proposal: ProposedCluster,
    rule_version: int = 1,
    commit: bool = True,
) -> StoryClusterRow:
    """Create or update a cluster ATOMICALLY, preserving its id.

    Membership assignment (``articles.cluster_id``), the cluster row, and the accepted
    edges all move in ONE transaction — a half-assigned cluster is never observable.
    """
    existing = find_existing_cluster_for_members(session, list(proposal.member_ids))
    cluster_id = existing.id if existing else cluster_id_from_anchor(proposal.anchor_id)

    row = session.get(StoryClusterRow, cluster_id)
    now = _now_iso()

    if row is None:
        row = StoryClusterRow(
            id=cluster_id,
            anchor_article_id=proposal.anchor_id,
            formed_at=now,
            method="deterministic",
        )
        session.add(row)
    # NOTE: anchor_article_id is NEVER reassigned on an existing row — the id is derived
    # from it, so changing it would churn the identity. That is the whole point of §8.

    row.representative_article_id = proposal.representative_id
    row.event_state = proposal.event_state
    row.sport = proposal.sport
    row.member_count = proposal.size
    row.rule_version = rule_version
    row.last_member_added_at = now

    # Membership — the ONLY column clustering touches on articles. Facts are untouched.
    for member_id in proposal.member_ids:
        art = session.get(ArticleRow, member_id)
        if art is not None:
            art.cluster_id = cluster_id

    _write_edges(session, cluster_id, proposal.edges)

    if commit:
        session.commit()
    return row


def persist_clusters(
    session: Session,
    proposals: list[ProposedCluster],
    rule_version: int = 1,
) -> list[StoryClusterRow]:
    """Persist a batch in one transaction (all-or-nothing)."""
    rows = [
        persist_cluster(session, p, rule_version=rule_version, commit=False)
        for p in proposals
    ]
    session.commit()
    return rows


def clear_clusters(session: Session, commit: bool = True) -> int:
    """Drop all cluster rows/edges and unassign membership.

    For idempotent RECOMPUTATION only (backfill, #102). It touches ``cluster_id`` and the
    cluster tables — never an article fact.
    """
    session.query(ArticleRow).filter(ArticleRow.cluster_id.isnot(None)).update(
        {ArticleRow.cluster_id: None}, synchronize_session=False
    )
    session.query(ClusterEdgeRow).delete(synchronize_session=False)
    removed = session.query(StoryClusterRow).delete(synchronize_session=False)
    if commit:
        session.commit()
    return removed
