"""
Stable formation-time cluster identity (issue #101) — docs/CLUSTERING.md §8.

    cluster_id = "cluster_" + sha1(anchor_article_id)[:16]

The id is a pure function of the ANCHOR (the founding member: earliest published_at,
tie -> lowest article id). It is assigned ONCE, when the cluster forms, and **never
churns** when members are appended.

WHY NOT CONTENT-ADDRESSED (``sha1(sorted member urls)``) — explicitly rejected:
a late-arriving article would change the membership hash, and therefore the id, and
therefore every downstream reference to it. Feed cards, feedback attribution, debug
traces, and QA diffs would all break on the arrival of a fourth source — the very
event clustering exists to handle. There is consequently **no ``superseded_by``** and
no id-churn machinery: there is no requirement for either.

The three operational-idempotency properties this buys (docs/CLUSTERING.md §8):
  1. repeated clustering creates no duplicate clusters;
  2. repeated clustering churns no existing ids;
  3. late arrivals append to the existing cluster atomically.
"""

import hashlib

_PREFIX = "cluster_"
_DIGEST_LEN = 16


def cluster_id_from_anchor(anchor_article_id: str) -> str:
    """Deterministic, stable-under-growth cluster id."""
    if not anchor_article_id:
        raise ValueError("anchor_article_id is required to mint a cluster id")
    digest = hashlib.sha1(anchor_article_id.encode("utf-8")).hexdigest()
    return f"{_PREFIX}{digest[:_DIGEST_LEN]}"


def edge_id(cluster_id: str, article_a: str, article_b: str) -> str:
    """Deterministic edge id, order-independent.

    Order-independent so re-running clustering cannot produce a duplicate row for the
    same undirected pair (idempotency property 1).
    """
    a, b = sorted((article_a, article_b))
    digest = hashlib.sha1(f"{cluster_id}|{a}|{b}".encode("utf-8")).hexdigest()
    return f"edge_{digest[:_DIGEST_LEN]}"
