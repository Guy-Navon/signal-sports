"""Id-listed removal of the wrong entities #415 (PR #421) stopped resolving; dry-run by default.

Stored rows keep the wrong alias match. For THESE ids only, this removes the named entity and,
where the sport came from that entity, takes the sport of a rules-only re-run. It adds nothing
the re-run found. Back up the live corpus first. Never a blanket backfill.

    python scripts/apply_415_alias_rows.py --db <db> --out <report.json>
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

KINGS, BULLS, HORNETS, BUCKS, NUGGETS = (
    "team:sacramento_kings", "team:chicago_bulls", "team:charlotte_hornets",
    "team:milwaukee_bucks", "team:denver_nuggets",
)
ROWS = {
    "rss_0bd13f8bf280c014f99a": KINGS, "rss_107dc1f0c42b0814de4a": KINGS,
    "rss_9a41875c1844b0689e97": KINGS, "rss_a05ba424866f61ca9a8a": KINGS,
    "rss_ace7e433aed4ddab105c": KINGS, "rss_d7dde66d32253ca89e2e": KINGS,
    "rss_dc605c6f6f9fa0a08a0d": KINGS, "rss_0d8f6ae9ccf54193ac2d": NUGGETS,
    "rss_b2972f6c0d4b11c73a68": NUGGETS, "rss_dee27d1f2d76030ed85c": NUGGETS,
    "rss_4708511141d9492f1dc6": BULLS, "rss_bfaa3523f05a524f7a51": BULLS,
    "rss_b850efe1b300764029bf": HORNETS, "rss_d04aff1bcc5cc625f5cd": HORNETS,
    "rss_5dabd7a89a68c806e760": BUCKS, "rss_71b0de50cb1c404dad7d": BUCKS,
    "rss_8c8622f10f140544aec7": BUCKS,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--i-know-this-is-the-live-corpus", action="store_true")
    args = parser.parse_args()

    os.environ["DATABASE_URL"] = f"sqlite:///{Path(args.db).resolve().as_posix()}"
    os.environ["CLASSIFICATION_PROVIDER"] = "disabled"
    os.environ["TRANSLATION_PROVIDER"] = "disabled"
    from app.db.corpus_protection import is_protected_corpus_db
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow
    from app.ingestion import ingestion_service
    from app.ingestion.adapters.base import RawSourceItem
    from app.ingestion.config import get_source_config
    from app.repositories import article_repository, profile_repository
    from app.services.preference_engine import score_article_v2
    from app.taxonomy.entities import ENTITIES

    if args.apply and is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
        parser.error("Live corpus writes require a backup and --i-know-this-is-the-live-corpus")

    report = []
    with SessionLocal() as session:
        profiles = {p: profile_repository.get_by_id(session, p) for p in ("guy", "casual_deni_fan")}
        for article_id, wrong in ROWS.items():
            article = article_repository.get_by_id(session, article_id)
            if article is None or wrong not in (article.entity_ids or []):
                report.append({"id": article_id, "status": "skipped"})
                continue
            item = RawSourceItem(source_id=article.source, url=article.url, title=article.title,
                                 published_at=None, summary=article.subtitle or "")
            rerun, _, _ = ingestion_service._normalise(item, get_source_config(article.source))
            if wrong in (rerun.entity_ids or []):
                report.append({"id": article_id, "status": "refused: re-run keeps it"})
                continue
            legacy = ENTITIES[wrong].legacy_name
            after = {
                "entity_ids": [e for e in article.entity_ids if e != wrong],
                "entities": [e for e in article.entities or [] if e != legacy],
                "sport": article.sport,
            }
            if article.sport == "basketball" and rerun.sport != "basketball":
                after["sport"] = rerun.sport
            trace = deepcopy(article.classification_trace or {})
            trace["correction_415"] = {"removed": wrong, "previous_sport": article.sport}
            after["classification_trace"] = trace
            corrected = article.model_copy(update=after)
            report.append({
                "id": article_id, "status": "correct", "title": article.title[:60],
                "removed": wrong, "sport": [article.sport, after["sport"]],
                "entity_ids": after["entity_ids"],
                "decisions": {p: [score_article_v2(article, v).decision,
                                  score_article_v2(corrected, v).decision]
                              for p, v in profiles.items()},
            })
            if args.apply:
                row = session.get(ArticleRow, article_id)
                for key, value in after.items():
                    setattr(row, key, value)
        if args.apply:
            session.commit()

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    done = sum(r["status"] == "correct" for r in report)
    print(f"{'Corrected' if args.apply else 'Would correct'} {done} of {len(ROWS)} rows; wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
