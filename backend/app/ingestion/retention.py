"""
Article retention cleanup (M7-3, #149) — the capability CLUSTERING.md §14
deliberately deferred, now built against its recorded constraints.

Feed visibility ≠ physical deletion. The consumer feed shows roughly the last
36 hours; several subsystems need LONGER retention: clustering (a late source
joins a story hours later; max cluster span is 72h), URL dedup (a purged URL
would be re-ingested as "new" — hence a retention window measured in WEEKS,
default 30 days, which exceeds any realistic RSS republish horizon), feedback
provenance (feedback rows reference article ids) and QA replay.

PROTECTIONS, in deletion order of authority:
  1. AGE — only rss_ articles published before the retention cutoff are
     candidates. Seeded demo articles (article_0xx) are never touched.
  2. CLUSTER COHESION — an article is protected while its cluster still has
     ANY in-window member: deleting part of a live story would corrupt the
     component the feed is still collapsing.
  3. FEEDBACK PROVENANCE — an article referenced by any feedback event is
     never deleted (learning attribution must stay replayable).
  4. NOTIFICATION LINEAGE needs no protection: ``notification_story_members``
     has no FK to articles BY DESIGN — it is the notification system's memory
     and must survive exactly this deletion.

Clusters whose members are ALL deleted are removed with their edges (a
grouping record with no members explains nothing); clusters that keep
in-window members keep their id (formation-time identity never churns) and
get their member_count refreshed.

GUARDED: runs only when RETENTION_CLEANUP_ENABLED=true, only through the
orchestration stage (or an explicit dry-run call); a failure degrades the
cycle to succeeded_with_warnings and never invalidates ingestion.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_DEFAULT_RETENTION_DAYS = 30


def cleanup_enabled() -> bool:
    return os.getenv("RETENTION_CLEANUP_ENABLED", "false").strip().lower() == "true"


def retention_days() -> int:
    try:
        v = int(os.getenv("ARTICLE_RETENTION_DAYS", str(_DEFAULT_RETENTION_DAYS)))
        return v if v >= 7 else _DEFAULT_RETENTION_DAYS   # never below a week:
        # the cluster span (72h) plus a safety margin must always fit inside.
    except ValueError:
        return _DEFAULT_RETENTION_DAYS


def cleanup_articles(session: Session, dry_run: bool = False) -> dict:
    """Delete out-of-window articles under the documented protections.

    Returns the cycle cleanup summary. ``dry_run=True`` computes everything
    and writes nothing (used by QA and the acceptance journey).
    """
    from app.db.orm_models import ArticleRow

    cutoff = (datetime.now(tz=timezone.utc)
              - timedelta(days=retention_days())).isoformat()

    candidates = {r[0] for r in session.execute(text(
        "SELECT id FROM articles WHERE id LIKE 'rss_%' AND published_at < :cutoff"
    ), {"cutoff": cutoff}).fetchall()}

    # Protection 2: a cluster with ANY in-window member protects ALL its members.
    protected_cluster = {r[0] for r in session.execute(text(
        "SELECT a.id FROM articles a WHERE a.cluster_id IS NOT NULL "
        "AND a.published_at < :cutoff AND a.cluster_id IN ("
        "  SELECT DISTINCT cluster_id FROM articles "
        "  WHERE cluster_id IS NOT NULL AND published_at >= :cutoff)"
    ), {"cutoff": cutoff}).fetchall()}

    # Protection 3: feedback provenance.
    referenced = {r[0] for r in session.execute(text(
        "SELECT DISTINCT article_id FROM feedback_events"
    )).fetchall()}
    protected_feedback = candidates & referenced

    deletable = candidates - protected_cluster - protected_feedback

    summary = {
        "dry_run": dry_run,
        "retention_days": retention_days(),
        "cutoff": cutoff,
        "candidates": len(candidates),
        "protected_cluster": len(protected_cluster & candidates),
        "protected_feedback": len(protected_feedback),
        "deleted": len(deletable),
        "clusters_removed": 0,
    }
    if dry_run or not deletable:
        return summary

    ids = list(deletable)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        session.query(ArticleRow).filter(ArticleRow.id.in_(chunk)).delete(
            synchronize_session=False)
    session.flush()

    # Remove clusters left with no members; refresh counts on survivors.
    orphaned = [r[0] for r in session.execute(text(
        "SELECT sc.id FROM story_clusters sc "
        "LEFT JOIN articles a ON a.cluster_id = sc.id "
        "GROUP BY sc.id HAVING COUNT(a.id) = 0"
    )).fetchall()]
    for cid in orphaned:
        session.execute(text("DELETE FROM cluster_edges WHERE cluster_id = :c"),
                        {"c": cid})
        session.execute(text("DELETE FROM story_clusters WHERE id = :c"), {"c": cid})
    session.execute(text(
        "UPDATE story_clusters SET member_count = "
        "(SELECT COUNT(*) FROM articles WHERE cluster_id = story_clusters.id)"
    ))
    session.commit()

    summary["clusters_removed"] = len(orphaned)
    logger.info("retention cleanup: deleted %d articles (protected: %d cluster, "
                "%d feedback), removed %d empty clusters",
                summary["deleted"], summary["protected_cluster"],
                summary["protected_feedback"], summary["clusters_removed"])
    return summary
