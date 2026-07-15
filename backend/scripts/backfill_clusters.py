"""
Cluster backfill + corpus QA (issue #102) — docs/CLUSTERING.md.

    # dry-run (DEFAULT — writes nothing to the target DB):
    .venv\\Scripts\\python.exe scripts/backfill_clusters.py --db data/corpus_copy.db

    # apply (explicit; REFUSED against the protected live corpus):
    .venv\\Scripts\\python.exe scripts/backfill_clusters.py --db data/corpus_copy.db --apply

SAFETY
------
- **Dry-run is the default.** It copies the target DB to a scratch file, runs the REAL
  backfill against the copy, reports, and deletes the copy. The target is never written.
  This makes dry-run exact (same code path) rather than an approximation.
- **--apply refuses the protected live corpus** (``app.db.corpus_protection``). QA and apply
  must target a COPY. The corpus is not in git and cannot be restored (#106).

ONE MATCHER
-----------
Backfill does NOT have its own matching semantics. It replays the LIVE ingestion stage
(``run_clustering_stage``) article-by-article in chronological order, which uses the same
``cluster_articles()`` and the same ``reconcile_scope()``. There is exactly one clustering
implementation; backfill and live cannot diverge.
"""

import argparse
import io
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fingerprint(path: Path) -> dict:
    st = path.stat()
    return {
        "path": str(path.resolve()),
        "size_bytes": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
    }


def _run_backfill(db_path: Path, rule_version: int) -> dict:
    """Backfill the DB at ``db_path`` (assumed safe to write) and return the report."""
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["CLUSTERING_ENABLED"] = "true"   # the flag governs the live scheduler, not QA

    from app.clustering.config import DEFAULT_CONFIG
    from app.clustering.ingest_stage import _to_input, run_clustering_stage
    from app.clustering.service import cluster_articles
    from app.db.database import SessionLocal, init_db
    from app.db.orm_models import ArticleRow
    from app.repositories import cluster_repository as repo

    init_db()
    session = SessionLocal()

    articles = (
        session.query(ArticleRow).order_by(ArticleRow.published_at, ArticleRow.id).all()
    )
    rss = [a for a in articles if a.id.startswith("rss_")]

    # ── BEFORE ────────────────────────────────────────────────────────────────
    before_clusters = {
        c.id: set(repo.get_member_ids(session, c.id))
        for c in repo.get_all_clusters(session)
    }
    before_clustered = {a.id for a in articles if a.cluster_id}

    # ── Replay the LIVE stage, chronologically ────────────────────────────────
    for art in articles:
        run_clustering_stage(session, [art.id], DEFAULT_CONFIG, rule_version=rule_version)

    # ── AFTER ─────────────────────────────────────────────────────────────────
    session.expire_all()
    after_rows = repo.get_all_clusters(session)
    after_clusters = {
        c.id: set(repo.get_member_ids(session, c.id)) for c in after_rows
    }
    articles = session.query(ArticleRow).all()
    after_clustered = {a.id for a in articles if a.cluster_id}

    created = sorted(set(after_clusters) - set(before_clusters))
    removed = sorted(set(before_clusters) - set(after_clusters))
    retained = sorted(set(after_clusters) & set(before_clusters))
    changed = sorted(
        cid for cid in retained if after_clusters[cid] != before_clusters[cid]
    )

    sizes = Counter(len(m) for m in after_clusters.values())
    members_total = sum(len(m) for m in after_clusters.values())

    # ── Bounded near-miss diagnostics (computed on demand, never persisted) ────
    inputs = [ci for ci in (_to_input(a) for a in articles) if ci is not None]
    diag = cluster_articles(inputs, DEFAULT_CONFIG, collect_rejections=True)
    near_miss = Counter(r.reason for r in diag.rejections)

    stamps = [a.published_at for a in rss if a.published_at]

    report = {
        "snapshot_timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "database": _fingerprint(db_path),
        "rule_version": rule_version,
        "matcher_config": {
            "max_story_coverage": DEFAULT_CONFIG.max_story_coverage,
            "df_ratio_max": DEFAULT_CONFIG.df_ratio_max,
            "tier_a": [DEFAULT_CONFIG.tier_a_jaccard_min, DEFAULT_CONFIG.tier_a_min_rare_tokens],
            "tier_b": [DEFAULT_CONFIG.tier_b_jaccard_min, DEFAULT_CONFIG.tier_b_min_rare_tokens],
            "tier_c": [DEFAULT_CONFIG.tier_c_jaccard_min, DEFAULT_CONFIG.tier_c_min_rare_tokens],
            "max_cluster_size": DEFAULT_CONFIG.max_cluster_size,
            "max_cluster_time_span_hours": DEFAULT_CONFIG.max_cluster_time_span_hours,
            "min_member_matches_to_join": DEFAULT_CONFIG.min_member_matches_to_join,
            "time_window_hours": DEFAULT_CONFIG.time_window_hours,
        },
        "corpus": {
            "total_articles": len(articles),
            "rss_articles": len(rss),
            "per_source": dict(Counter(a.source for a in rss).most_common()),
            "sport_distribution": dict(Counter(a.sport for a in rss).most_common()),
            "event_state_distribution": dict(Counter(a.event_type for a in rss).most_common()),
            "time_range": {"earliest": min(stamps) if stamps else None,
                           "latest": max(stamps) if stamps else None},
        },
        "clusters": {
            "proposed_count": len(after_clusters),
            "member_count": members_total,
            "size_distribution": {str(k): v for k, v in sorted(sizes.items())},
            "created": created,
            "retained": retained,
            "changed": changed,
            "removed": removed,
            "ids_preserved": len(retained),
        },
        "cards": {
            "before": len(articles) - len(before_clustered) + len(before_clusters),
            "after": len(articles) - len(after_clustered) + len(after_clusters),
        },
        "articles": {
            "newly_clustered": sorted(after_clustered - before_clustered),
            "newly_unclustered": sorted(before_clustered - after_clustered),
        },
        "near_miss_reasons": dict(near_miss.most_common()),
        "detail": [
            {
                "cluster_id": c.id,
                "event_state": c.event_state,
                "sport": c.sport,
                "anchor": c.anchor_article_id,
                "representative": c.representative_article_id,
                "rule_version": c.rule_version,
                "members": [
                    {
                        "id": m.id,
                        "source": m.source,
                        "title": m.title,
                        "sport": m.sport,
                        "event_type": m.event_type,
                        "published_at": m.published_at,
                    }
                    for m in repo.get_members(session, c.id)
                ],
                "edges": [
                    {
                        "a": e.article_a, "b": e.article_b, "tier": e.tier,
                        "jaccard": e.jaccard, "hours_apart": e.hours_apart,
                        "rare_tokens": e.rare_tokens,
                        "entity_overlap": e.entity_overlap,
                    }
                    for e in repo.get_edges(session, c.id)
                ],
            }
            for c in after_rows
        ],
    }
    session.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="target sqlite DB path")
    parser.add_argument("--apply", action="store_true",
                        help="WRITE to the target DB (default is dry-run)")
    parser.add_argument("--i-know-this-is-the-live-corpus", action="store_true",
                        help="#126 activation only: allow --apply against the protected "
                             "live corpus (requires a fresh verified backup first)")
    parser.add_argument("--rule-version", type=int, default=1)
    parser.add_argument("--out", help="write the JSON report here")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"no such database: {db_path}")

    if args.apply:
        # Corpus protection (#106): the live corpus is not in git and cannot be restored.
        # The #126 activation gate is the ONE sanctioned live write — behind the same
        # explicit opt-in flag as the other guarded corpus writers, never by default.
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        from app.db.corpus_protection import is_protected_corpus_db

        if is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
            raise SystemExit(
                f"REFUSED: --apply targets the protected live corpus ({db_path}).\n"
                "Backfill must run against a COPY:\n"
                "  cp data/signal_sports.db data/corpus_copy.db\n"
                "  python scripts/backfill_clusters.py --db data/corpus_copy.db --apply\n"
                "(#126 activation only: add --i-know-this-is-the-live-corpus)"
            )
        target, scratch = db_path, None
        mode = "APPLY"
    else:
        # Exact dry-run: run the REAL backfill against a throwaway copy.
        scratch = Path(tempfile.mkdtemp(prefix="cluster_dryrun_")) / db_path.name
        shutil.copyfile(db_path, scratch)
        target, mode = scratch, "DRY-RUN"

    report = _run_backfill(target, args.rule_version)
    report["mode"] = mode
    report["target_database"] = _fingerprint(db_path)

    if scratch is not None:
        shutil.rmtree(scratch.parent, ignore_errors=True)

    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    c, cl = report["corpus"], report["clusters"]
    print(f"\n=== cluster backfill [{mode}] ===", file=out)
    print(f"db          : {report['target_database']['path']}", file=out)
    print(f"rule_version: {report['rule_version']}", file=out)
    print(f"articles    : {c['total_articles']} ({c['rss_articles']} rss)", file=out)
    print(f"per source  : {c['per_source']}", file=out)
    print(f"clusters    : {cl['proposed_count']}  members={cl['member_count']}  "
          f"sizes={cl['size_distribution']}", file=out)
    print(f"created={len(cl['created'])} retained={len(cl['retained'])} "
          f"changed={len(cl['changed'])} removed={len(cl['removed'])} "
          f"ids_preserved={cl['ids_preserved']}", file=out)
    print(f"cards       : {report['cards']['before']} -> {report['cards']['after']}", file=out)
    print(f"near misses : {report['near_miss_reasons']}", file=out)
    out.flush()

    if args.out:
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
        print(f"report -> {args.out}", file=out)
        out.flush()


if __name__ == "__main__":
    main()
