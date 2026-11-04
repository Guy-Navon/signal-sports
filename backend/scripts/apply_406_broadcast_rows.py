"""Id-listed correction of the stored rows #406 moved off `schedule`; dry-run by default.

#406 (PR #412) narrowed `schedule`: a broadcast word counts only when it announces a
broadcast. Stored rows keep their old facts, so seven reviewed rows are still `schedule`.
This re-runs the deterministic ingestion path (`_normalise`, LLM and translation disabled,
the path all seven were stored by: none carries an LLM proposal) on THESE ids only:

- a row is corrected only if it is stored `schedule` and the re-run is not;
- only the event fields are written (event_type, event_certainty, importance, tags and the
  trace's `event` block, which records the correction);
- sport, league, entities, entity_ids and competitions must reproduce exactly, or the row
  is refused rather than half-rewritten.

Apply requires the exact dry-run report to have been reviewed; changed inputs or proposals
abort before any write. Back up the live corpus with backup_db.py first. Never a blanket
backfill: ids outside IDS are never read.

    python scripts/apply_406_broadcast_rows.py --db <copy> --out <report.json>
"""

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Reviewed on PR #412 (frozen 2026-11-01 copy and the 2026-11-02 live backup).
IDS = (
    "rss_912dce7a909f03a572d3",  # Barkley cries on air (census #3 fit: feed)
    "rss_716522fea9325b2274d9",  # Yamal speech gaffe on air
    "rss_b9603030dbf28b5ff942",  # Ronaldo-linked journalist explodes on air
    "rss_683f51bce51320c12389",  # Robbie Williams on air
    "rss_7bbbbd1129290665c229",  # Netflix buys World Cup 2030 rights (ynet); re-run: signing, #413
    "rss_1a948eeea90c3626e71d",  # Netflix buys World Cup 2030 rights (walla)
    "rss_033456324a3b5c791540",  # women's athletics broadcasts to change
)

# Facts the correction does not own: they must reproduce or the row is refused.
_PRESERVED = ("sport", "league", "entities", "entity_ids", "primary_competition",
              "article_competitions")
_WRITTEN = ("event_type", "event_certainty", "importance", "tags")


def _rerun(article):
    from app.ingestion import ingestion_service
    from app.ingestion.adapters.base import RawSourceItem
    from app.ingestion.config import get_source_config

    item = RawSourceItem(source_id=article.source, url=article.url, title=article.title,
                         published_at=None, summary=article.subtitle or "")
    rerun, _llm_ms, _gate = ingestion_service._normalise(item, get_source_config(article.source))
    return rerun


def plan_correction(article):
    """The proposed change for one stored article, a refusal, or None (nothing to do)."""
    if article.event_type != "schedule":
        return None
    rerun = _rerun(article)
    if rerun.event_type == "schedule":
        return None
    for field in _PRESERVED:
        if getattr(rerun, field) != getattr(article, field):
            return {"id": article.id, "refused": field,
                    "stored": getattr(article, field), "rerun": getattr(rerun, field)}
    trace = deepcopy(article.classification_trace or {})
    trace["event"] = dict((rerun.classification_trace or {}).get("event") or {})
    trace["event"]["correction"] = {"issue": 406, "previous_event": article.event_type}
    after = {field: getattr(rerun, field) for field in _WRITTEN}
    after["classification_trace"] = trace
    return {
        "id": article.id,
        "before": {field: getattr(article, field) for field in _WRITTEN},
        "after": after,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--ids", nargs="+", help="a subset of IDS (default: all of them)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewed-report")
    parser.add_argument("--i-know-this-is-the-live-corpus", action="store_true")
    args = parser.parse_args()

    ids = tuple(args.ids or IDS)
    unknown = sorted(set(ids) - set(IDS))
    if unknown:
        parser.error(f"not in the reviewed id list: {unknown}")

    os.environ["DATABASE_URL"] = f"sqlite:///{Path(args.db).resolve().as_posix()}"
    os.environ["CLASSIFICATION_PROVIDER"] = "disabled"
    os.environ["TRANSLATION_PROVIDER"] = "disabled"
    from app.db.corpus_protection import is_protected_corpus_db
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow
    from app.repositories import article_repository

    if args.apply and is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
        parser.error("Live corpus writes require a backup and --i-know-this-is-the-live-corpus")

    with SessionLocal() as session:
        rows, missing = [], []
        for article_id in ids:
            article = article_repository.get_by_id(session, article_id)
            if article is None:
                missing.append(article_id)
                continue
            plan = plan_correction(article)
            if plan is not None:
                plan["input"] = article.model_dump(mode="json")
                rows.append(json.loads(json.dumps(plan, ensure_ascii=False, default=str)))
        refused = [r for r in rows if "refused" in r]
        changes = [r for r in rows if "refused" not in r]
        if args.apply:
            if not args.reviewed_report:
                parser.error("--apply requires --reviewed-report from an inspected dry run")
            reviewed = json.loads(Path(args.reviewed_report).read_text(encoding="utf8"))
            if reviewed["rows"] != changes or reviewed["ids"] != list(ids):
                parser.error("Inputs or proposals changed since review; produce and review a new dry run")
            for change in changes:
                row = session.get(ArticleRow, change["id"])
                for key, value in change["after"].items():
                    setattr(row, key, value)
            session.commit()

    report = {"applied": args.apply, "ids": list(ids), "missing": missing,
              "refused": refused, "rows": changes}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"{'Applied' if args.apply else 'Would correct'} {len(changes)} rows "
          f"({len(refused)} refused, {len(missing)} missing); wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
