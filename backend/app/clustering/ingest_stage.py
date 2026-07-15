"""
Live clustering stage for ingestion (issue #101) — docs/CLUSTERING.md.

Runs AFTER classification and article insert:

    fetch → source filtering → URL dedup → classification/facts → insert → [THIS]

It is a thin adapter, NOT a second algorithm. It loads a bounded candidate window,
hands it to the SAME ``cluster_articles()`` the backfill (#102) uses, and persists the
result through the SAME ``reconcile_scope()``. There is exactly one clustering
implementation; live and backfill cannot drift apart because there is nothing to drift.

ROLLOUT: disabled by default (``CLUSTERING_ENABLED=false``), using the repository's
established env-flag mechanism (cf. ``CLASSIFICATION_LLM_GATING``, ``ALLOW_DEV_RESET``).
The live scheduler must not cluster the real corpus until the Checkpoint-2 QA gate (#102)
passes.

FAILURE SEMANTICS: clustering is a quality-enhancement stage and must never corrupt
ingestion. Articles are committed per-item by ``article_repository.insert`` — that is the
existing run-accounting contract, in which one bad item is counted and the run continues.
Clustering therefore follows the same contract: if the stage fails, the transaction is
rolled back, the ARTICLES SURVIVE UNCLUSTERED, and the failure is reported on the run
result. Rolling back a correctly classified and inserted article because *grouping* failed
would be strictly worse. Because the stage commits exactly ONCE at the end, a failure can
never leave partially persisted clusters or edges.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.clustering.config import DEFAULT_CONFIG, ClusteringConfig
from app.clustering.contract import ClusterInput
from app.clustering.service import cluster_articles
from app.db.orm_models import ArticleRow
from app.repositories import cluster_repository as cluster_repo

logger = logging.getLogger(__name__)

# The rule generation these clusters were produced by. Bump when matcher semantics change;
# a rule change is then an explicit, auditable recompute (#102), never silent drift.
RULE_VERSION = 1


def clustering_enabled() -> bool:
    """Env-flag rollout, matching the repo's existing mechanism. Default OFF."""
    return os.environ.get("CLUSTERING_ENABLED", "false").strip().lower() == "true"


@dataclass
class ClusterStageResult:
    ran: bool = False
    clusters_created: int = 0
    articles_appended: int = 0          # newly-inserted articles that joined a cluster
    articles_unclustered: int = 0       # newly-inserted articles left alone
    clusters_removed: int = 0
    window_size: int = 0
    failed: bool = False
    error: Optional[str] = None
    created_cluster_ids: list[str] = field(default_factory=list)
    retained_cluster_ids: list[str] = field(default_factory=list)


def _parse(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def _to_input(row: ArticleRow) -> Optional[ClusterInput]:
    published = _parse(row.published_at)
    if published is None:
        return None
    return ClusterInput(
        id=row.id,
        source=row.source,
        title=row.title or "",
        published_at=published,
        sport=row.sport or "unknown",
        event_type=row.event_type or "news",
        event_certainty=row.event_certainty,
        entity_ids=tuple(row.entity_ids or ()),
        primary_competition=row.primary_competition,
        subtitle=row.subtitle or "",
        story_anchors=tuple(row.story_anchors or ()),
    )


def load_candidate_window(
    session: Session,
    new_article_ids: list[str],
    cfg: ClusteringConfig = DEFAULT_CONFIG,
) -> list[ArticleRow]:
    """The BOUNDED candidate window for a set of newly-inserted articles.

    Bounded by the largest configured event-state lookback (there is no minimum corpus
    size — the matcher works on a small rolling window by design, §7.3).

    Then HYDRATES full membership of every existing cluster the window touches: a cluster
    whose members fall partly outside the time window must never be evaluated incompletely,
    or coherence would judge a cluster it cannot see.
    """
    if not new_article_ids:
        return []

    new_rows = (
        session.query(ArticleRow).filter(ArticleRow.id.in_(new_article_ids)).all()
    )
    stamps = [t for t in (_parse(r.published_at) for r in new_rows) if t is not None]
    if not stamps:
        return []

    max_lookback = max(cfg.time_window_hours.values()) if cfg.time_window_hours else 24.0
    lo = (min(stamps) - timedelta(hours=max_lookback)).isoformat()
    hi = (max(stamps) + timedelta(hours=max_lookback)).isoformat()

    window = (
        session.query(ArticleRow)
        .filter(ArticleRow.published_at >= lo, ArticleRow.published_at <= hi)
        .all()
    )

    by_id = {r.id: r for r in window}
    for r in new_rows:
        by_id.setdefault(r.id, r)

    # Hydrate any cluster the window touches, so coherence never sees a partial cluster.
    touched = {r.cluster_id for r in by_id.values() if r.cluster_id}
    if touched:
        for r in (
            session.query(ArticleRow)
            .filter(ArticleRow.cluster_id.in_(touched))
            .all()
        ):
            by_id.setdefault(r.id, r)

    return list(by_id.values())


@dataclass
class AnchorStageResult:
    ran: bool = False
    enriched: int = 0
    skipped_current: int = 0        # already at the current validator version
    anchors_persisted: int = 0
    failed: bool = False
    error: Optional[str] = None


def run_anchor_enrichment_stage(
    session: Session,
    new_article_ids: list[str],
    cfg: ClusteringConfig = DEFAULT_CONFIG,
) -> AnchorStageResult:
    """Persist validated story anchors for freshly inserted articles (#141).

    ALWAYS ON — this is fact enrichment, not clustering behaviour: validation runs
    ONCE here (deterministic, offline wordfreq lookups; no model, no network) and
    pair evaluation only ever READS the persisted result. `CLUSTERING_ENABLED`
    governs grouping, not enrichment, so anchors are already in place whenever #126
    flips the flag.

    Fail-safe on two levels: if the frequency resource is missing the validator
    abstains per candidate (canonical taxonomy anchors still persist), and a stage
    failure is reported, never propagated — ingestion must not be corrupted by an
    enrichment stage.
    """
    from app.clustering.anchor_enrichment import (
        enrich_article_anchors, hard_gate_population,
    )
    from app.clustering.anchor_validators import LexicalFrequencyValidator

    result = AnchorStageResult()
    if not new_article_ids:
        return result
    try:
        validator = LexicalFrequencyValidator()
        version = validator.validator_version

        rows = load_candidate_window(session, new_article_ids, cfg)
        inputs = {r.id: _to_input(r) for r in rows}
        peers = [ci for ci in inputs.values() if ci is not None]

        new_rows = [r for r in rows if r.id in set(new_article_ids)]
        for row in new_rows:
            if row.anchor_validator_version == version:
                result.skipped_current += 1
                continue
            anchor = inputs.get(row.id)
            if anchor is None:
                continue
            population = hard_gate_population(anchor, peers, cfg)
            stored, _ = enrich_article_anchors(
                row.title or "", row.subtitle or "", validator,
                article_id=row.id, population=population,
            )
            row.story_anchors = [sa.to_json() for sa in stored]
            row.anchor_validator_version = version
            result.enriched += 1
            result.anchors_persisted += len(stored)
        session.commit()
        result.ran = True
        return result
    except Exception as exc:                              # pragma: no cover - defensive
        session.rollback()
        logger.error("Anchor enrichment failed (articles kept, unenriched): %s", exc)
        result.ran = True
        result.failed = True
        result.error = str(exc)
        return result


def run_clustering_stage(
    session: Session,
    new_article_ids: list[str],
    cfg: ClusteringConfig = DEFAULT_CONFIG,
    rule_version: int = RULE_VERSION,
) -> ClusterStageResult:
    """Cluster the bounded window around freshly inserted articles.

    Never raises: a clustering failure is reported, not propagated — ingestion must not be
    corrupted by a quality-enhancement stage.
    """
    result = ClusterStageResult()
    if not clustering_enabled() or not new_article_ids:
        return result

    try:
        rows = load_candidate_window(session, new_article_ids, cfg)
        inputs = [ci for ci in (_to_input(r) for r in rows) if ci is not None]
        result.window_size = len(inputs)
        if len(inputs) < 2:
            result.ran = True
            result.articles_unclustered = len(new_article_ids)
            return result

        matched = cluster_articles(inputs, cfg)

        scope_ids = {ci.id for ci in inputs}
        rec = cluster_repo.reconcile_scope(
            session, scope_ids, matched.clusters, rule_version=rule_version
        )

        clustered = set(rec.clustered_article_ids)
        new_ids = set(new_article_ids)

        result.ran = True
        result.clusters_created = len(rec.created_cluster_ids)
        result.clusters_removed = len(rec.removed_cluster_ids)
        result.articles_appended = len(new_ids & clustered)
        result.articles_unclustered = len(new_ids - clustered)
        result.created_cluster_ids = rec.created_cluster_ids
        result.retained_cluster_ids = rec.retained_cluster_ids
        return result

    except Exception as exc:                              # pragma: no cover - defensive
        # ONE commit happens inside reconcile_scope; rolling back here guarantees no
        # partially persisted clusters or edges. The ARTICLES survive, unclustered.
        session.rollback()
        logger.error("Clustering stage failed (articles kept, unclustered): %s", exc)
        result.ran = True
        result.failed = True
        result.error = str(exc)
        result.articles_unclustered = len(new_article_ids)
        return result
