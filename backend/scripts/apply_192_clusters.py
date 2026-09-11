"""Reconcile only memberships affected by reviewed #191/#192 corrections.

Dry run computes in a transaction and rolls it back. Apply recomputes the same
proposals and requires an exact reviewed report before the single commit.
Candidate windows and matcher are shared with ingestion; unrelated clusters in
those windows are excluded from persistence. No article facts or outbox writes.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def reconcile_affected(session, affected):
    from app.clustering.ingest_stage import load_candidate_window, _to_input, RULE_VERSION
    from app.clustering.service import cluster_articles
    from app.db.orm_models import ArticleRow
    from app.repositories import cluster_repository
    steps = []
    for aid in sorted(affected):
        rows = load_candidate_window(session, [aid])
        inputs = [ci for r in rows if (ci := _to_input(r)) is not None]
        proposals = cluster_articles(inputs).clusters
        scope = {aid}
        # Close over both existing and proposed memberships. Never reconcile a
        # partial cluster, and never write an unrelated match from the window.
        while True:
            previous = set(scope)
            old_clusters = {r.cluster_id for r in rows if r.id in scope and r.cluster_id}
            scope.update(r.id for r in rows if r.cluster_id in old_clusters)
            for p in proposals:
                if scope.intersection(p.member_ids):
                    scope.update(p.member_ids)
            if scope == previous:
                break
        selected = [p for p in proposals if scope.intersection(p.member_ids)]
        before = {r.id: r.cluster_id for r in rows if r.id in scope}
        cluster_repository.reconcile_scope(session, scope, selected, rule_version=RULE_VERSION, commit=False)
        session.flush()
        after = {r.id: r.cluster_id for r in session.query(ArticleRow).filter(ArticleRow.id.in_(scope))}
        if before != after:
            steps.append({"trigger": aid, "before": before, "after": after,
                          "proposals": [asdict(p) for p in selected]})
    return steps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--corrections", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewed-report")
    parser.add_argument("--i-know-this-is-the-live-corpus", action="store_true")
    args = parser.parse_args()
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(args.db).resolve().as_posix()}"
    from app.db.corpus_protection import is_protected_corpus_db
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow
    if args.apply and is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
        parser.error("Back up first and acknowledge the protected corpus")
    affected = {r["id"] for path in args.corrections
                for r in json.loads(Path(path).read_text(encoding="utf8"))["rows"]}
    with SessionLocal() as session:
        rows = session.query(ArticleRow).order_by(ArticleRow.id).all()
        inputs = [{c.name: getattr(row, c.name) for c in ArticleRow.__table__.columns} for row in rows]
        fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()
        report = {"input_sha256": fingerprint, "affected_ids": sorted(affected),
                  "steps": reconcile_affected(session, affected)}
        # Normalize tuples/datetimes before comparing JSON review artifacts.
        report = json.loads(json.dumps(report, default=str))
        if args.apply:
            if not args.reviewed_report or json.loads(Path(args.reviewed_report).read_text(encoding="utf8")) != report:
                session.rollback()
                parser.error("Apply requires an exact, unchanged --reviewed-report")
            session.commit()
        else:
            session.rollback()
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"{'Applied' if args.apply else 'Proposed'} {len(report['steps'])} membership changes")


if __name__ == "__main__":
    main()
