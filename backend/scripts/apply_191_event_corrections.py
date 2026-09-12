"""Reviewable event-only corrections for #191; dry-run by default.

No classifier/resolver backfill: only the newly connected editorial/relocation
routes and the already-shipped Grand Slam assertion route are considered.
Other stored facts, including LLM-assisted sport and entities, are preserved.
Apply requires the exact dry-run report to have been reviewed; a changed input
or proposal aborts before writes. Back up the live corpus with backup_db.py first.
"""

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def correction(article):
    from app.classification.event_subjects import relocation_subject_ids
    from app.classification.event_evidence import validate_event_evidence
    from app.ingestion.classifier import detect_article_event, _assign_importance, _collect_tags

    title = article.title.lower()
    subtitle = (article.subtitle or "").lower()
    evidence = detect_article_event(title, subtitle, article.sport)
    title_supported = validate_event_evidence(evidence.event_type, title, sport=article.sport).valid
    in_scope = evidence.event_type in {"analysis", "interview", "relocation"}
    if article.event_type == "title_win" and article.sport == "tennis":
        slam = validate_event_evidence("grand_slam_winner", title, sport="tennis")
        if slam.valid:
            evidence, title_supported, in_scope = slam, True, True
    if not in_scope or evidence.event_type == article.event_type:
        return None
    # Keep the same combined-text guard as normal ingestion, including blockers.
    checked = validate_event_evidence(evidence.event_type, title + " " + subtitle, sport=article.sport)
    if not checked.valid:
        return None
    certainty = evidence.certainty if title_supported else "probable"
    trace = deepcopy(article.classification_trace or {})
    trace["event"] = {
        "proposed": evidence.event_type, "final": evidence.event_type,
        "certainty": certainty, "validated_after_facts": True,
        "corrected": False, "abstention_reason": None,
        "correction": {"issue": 191, "previous_event": article.event_type},
    }
    if evidence.event_type == "relocation":
        trace["event"]["subject_entity_ids"] = relocation_subject_ids(title, article.entity_ids)
    return {
        "event_type": evidence.event_type, "event_certainty": certainty,
        "importance": _assign_importance(evidence.event_type, article.entities, article.league, certainty),
        "tags": _collect_tags(article.sport, article.league, article.entities, evidence.event_type),
        "classification_trace": trace,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewed-report")
    parser.add_argument("--i-know-this-is-the-live-corpus", action="store_true")
    args = parser.parse_args()
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(args.db).resolve().as_posix()}"
    from app.db.database import SessionLocal
    from app.db.corpus_protection import is_protected_corpus_db
    from app.db.orm_models import ArticleRow
    from app.repositories import article_repository
    if args.apply and is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
        parser.error("Live corpus writes require a backup and --i-know-this-is-the-live-corpus")
    with SessionLocal() as session:
        changes = []
        for article in article_repository.get_rss_articles(session):
            after = correction(article)
            if after:
                changes.append({"id": article.id, "input": article.model_dump(mode="json"), "after": after})
        changes.sort(key=lambda r: r["id"])
        if args.apply:
            if not args.reviewed_report:
                parser.error("--apply requires --reviewed-report from an inspected dry run")
            reviewed = json.loads(Path(args.reviewed_report).read_text(encoding="utf8"))
            if reviewed["rows"] != changes:
                parser.error("Inputs or proposals changed since review; produce and review a new dry run")
            for change in changes:
                row = session.get(ArticleRow, change["id"])
                for key, value in change["after"].items():
                    setattr(row, key, value)
            session.commit()
    Path(args.out).write_text(json.dumps({"applied": args.apply, "rows": changes}, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"{'Applied' if args.apply else 'Would correct'} {len(changes)} event-only rows; wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
