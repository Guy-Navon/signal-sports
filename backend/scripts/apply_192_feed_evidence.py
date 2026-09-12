"""Targeted #192 evidence refresh, with exact-report review before applying.

Adds only newly validated title transaction-subject anchors. Attention evidence
is refreshed only for this corpus's current push articles (both demo profiles).
Does not reclassify, resolve entities, change profiles or dispatch notifications.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def added_subject_anchors(article, validator):
    from app.clustering.anchors import generate_candidates
    existing = {a["anchor"] for a in article.story_anchors or []}
    added = []
    for candidate in generate_candidates(article.title, article.subtitle or "", article_id=article.id):
        if candidate.generation_rule != "transaction_subject" or candidate.role not in {"subject", "unknown", "quoted"}:
            continue
        decision = validator.validate(candidate)
        if decision.is_accepted and decision.normalized_anchor not in existing:
            added.append({"anchor": decision.normalized_anchor, "role": candidate.role,
                          "source": candidate.source, "validator_id": decision.validator_id,
                          "reason_code": decision.reason_code})
            existing.add(decision.normalized_anchor)
    return added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewed-report")
    parser.add_argument("--i-know-this-is-the-live-corpus", action="store_true")
    args = parser.parse_args()
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(args.db).resolve().as_posix()}"
    from app.classification.attention_evidence import attention_evidence
    from app.clustering.anchor_validators import LexicalFrequencyValidator
    from app.db.corpus_protection import is_protected_corpus_db
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow
    from app.repositories import article_repository, profile_repository
    from app.services.preference_engine import score_article_v2
    if args.apply and is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
        parser.error("Back up first and acknowledge the protected corpus")
    validator = LexicalFrequencyValidator()
    if not validator.available():
        parser.error("Anchor validator unavailable")
    with SessionLocal() as session:
        profiles = [profile_repository.get_by_id(session, uid) for uid in ("guy", "casual_deni_fan")]
        changes = []
        for article in article_repository.get_rss_articles(session):
            row = session.get(ArticleRow, article.id)
            after = {}
            added = added_subject_anchors(row, validator)
            if added:
                after["story_anchors"] = list(row.story_anchors or []) + added
            if any(p and score_article_v2(article, p).decision == "push" for p in profiles):
                attention = attention_evidence(article.title, article.subtitle, article.event_type, article.entity_ids)
                trace = deepcopy(article.classification_trace or {})
                if trace.get("attention") != attention:
                    trace["attention"] = attention
                    after["classification_trace"] = trace
            if after:
                changes.append({"id": article.id, "input": article.model_dump(mode="json"),
                                "anchors_before": row.story_anchors, "after": after})
        changes.sort(key=lambda r: r["id"])
        if args.apply:
            if not args.reviewed_report:
                parser.error("--apply requires --reviewed-report")
            if json.loads(Path(args.reviewed_report).read_text(encoding="utf8"))["rows"] != changes:
                parser.error("Inputs/proposals changed after review")
            for change in changes:
                row = session.get(ArticleRow, change["id"])
                for key, value in change["after"].items():
                    setattr(row, key, value)
            session.commit()
    Path(args.out).write_text(json.dumps({"applied": args.apply, "rows": changes}, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"{'Applied' if args.apply else 'Would refresh'} {len(changes)} evidence rows; wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
