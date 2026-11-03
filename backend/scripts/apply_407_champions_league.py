"""Correct the 11 stored rows #407 reclassifies (the shared "ליגת האלופות" name).

#407 changes NEW classification only: stored rows keep football / comp:ucl or a missing
competition. This script re-runs the deterministic ingestion path (LLM and translation
disabled; no LLM call) on EXACTLY the rows listed below, which are the rows whose facts the
#407 corpus rerun changed (frozen 2026-11-01 copy, 3,877 rows), and rewrites only the facts
#407 changes: sport, league, primary_competition, article_competitions, entity_ids, entities
and the classification trace.

A row is refused, never half-corrected, when:
  - its stored facts did not come from the rules path (``classified_by != "rules"``): a
    rules-only rerun would drop LLM-assisted facts (N05 finding F-N05-6);
  - the rerun would change anything else (event_type, importance): that is not #407's
    delta and must not be laundered in as a correction.

Story clusters are not recomputed. Every listed row is older than the feed window.

DRY RUN BY DEFAULT. ``--apply`` writes; the protected live corpus (#106) additionally
requires ``--i-know-this-is-the-live-corpus`` (back up first).

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts/apply_407_champions_league.py --db <copy.db> --out <log.json>
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROW_IDS = (
    "rss_fd09dded9f014f7025c7",
    "rss_0d2787d52512b38355fc",
    "rss_b9898e909910f1abdd95",
    "rss_9bfa06aac93b6a54c642",
    "rss_3bb8d9649f93d5db896d",
    "rss_7e6818fc2784105ec7f8",
    "rss_a9780ab3a7ef7b05d180",
    "rss_b3d029445e062c3a4b1c",
    "rss_a5ac5e115e59862b6a5f",
    "rss_9d5c0581c673323c5989",
    "rss_69cf8173f9af8c9a754f",
)

REWRITTEN_FIELDS = (
    "sport", "league", "primary_competition", "article_competitions", "entity_ids", "entities",
)
_MUST_NOT_CHANGE = ("event_type", "importance")


def plan_row(stored: dict, rerun) -> dict:
    """Plan one row. ``stored``: the row's current facts; ``rerun``: the Article the
    deterministic path produces now. Returns {"status": correct|unchanged|refused, ...}."""
    if stored.get("classified_by") != "rules":
        return {"status": "refused",
                "reason": f"classified_by={stored.get('classified_by')!r}: a rules-only rerun "
                          "would drop LLM-assisted facts"}
    for field in _MUST_NOT_CHANGE:
        if stored.get(field) != getattr(rerun, field):
            return {"status": "refused",
                    "reason": f"{field} would change ({stored.get(field)!r} -> "
                              f"{getattr(rerun, field)!r}); not part of #407"}
    before = {f: stored.get(f) for f in REWRITTEN_FIELDS}
    after = {f: (list(getattr(rerun, f)) if isinstance(getattr(rerun, f), list)
                 else getattr(rerun, f)) for f in REWRITTEN_FIELDS}
    if before == after:
        return {"status": "unchanged"}
    return {"status": "correct",
            "before": {f: v for f, v in before.items() if v != after[f]},
            "after": {f: v for f, v in after.items() if v != before[f]}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--i-know-this-is-the-live-corpus", action="store_true")
    ap.add_argument("--out", help="write the row-by-row JSON log here")
    args = ap.parse_args()

    db = Path(args.db).resolve()
    os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
    os.environ["CLASSIFICATION_PROVIDER"] = "disabled"   # never an LLM call
    os.environ["TRANSLATION_PROVIDER"] = "disabled"

    from app.db.corpus_protection import is_protected_corpus_db
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow
    from app.ingestion import ingestion_service
    from app.ingestion.adapters.base import RawSourceItem
    from app.ingestion.config import get_source_config
    from app.repositories import article_repository, profile_repository
    from app.services.freshness import DEFAULT_FEED_MAX_AGE_HOURS
    from app.services.preference_engine import score_article_v2

    protected = is_protected_corpus_db()
    if args.apply and protected and not args.i_know_this_is_the_live_corpus:
        print("Refusing: that is the live corpus. Re-run with "
              "--i-know-this-is-the-live-corpus once a backup exists.")
        return 2

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=DEFAULT_FEED_MAX_AGE_HOURS)
    log = []
    with SessionLocal() as session:
        profiles = {p.user_id: p for p in profile_repository.get_all(session)}
        scored = [u for u in ("guy", "casual_deni_fan") if u in profiles]
        for row_id in ROW_IDS:
            row = session.get(ArticleRow, row_id)
            if row is None:
                log.append({"id": row_id, "status": "missing"})
                continue
            old_article = article_repository._row_to_article(row)
            cfg = get_source_config(row.source)
            rerun, _, _ = ingestion_service._normalise(
                RawSourceItem(source_id=row.source, url=row.url, title=row.title,
                              published_at=None, summary=row.subtitle or ""), cfg)
            stored = {f: getattr(row, f) for f in (*REWRITTEN_FIELDS, *_MUST_NOT_CHANGE)}
            stored["classified_by"] = row.classified_by
            plan = plan_row(stored, rerun)
            published = old_article.published_at
            if published is not None and published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            entry = {"id": row_id, "title": row.title, **plan,
                     "published_at": published.isoformat() if published else None,
                     "in_feed_window": bool(published and published >= window_start)}
            if plan["status"] == "correct":
                new_article = old_article.model_copy(update={
                    **{f: getattr(rerun, f) for f in REWRITTEN_FIELDS},
                    "classification_trace": rerun.classification_trace,
                    "taxonomy_version": rerun.taxonomy_version,
                })
                entry["decisions"] = {
                    u: [score_article_v2(old_article, profiles[u]).decision,
                        score_article_v2(new_article, profiles[u]).decision]
                    for u in scored
                }
                if args.apply:
                    for f in REWRITTEN_FIELDS:
                        setattr(row, f, getattr(rerun, f))
                    row.classification_trace = rerun.classification_trace
                    row.taxonomy_version = rerun.taxonomy_version
            log.append(entry)
        if args.apply:
            session.commit()

    verb = "corrected" if args.apply else "would correct"
    counts = {s: sum(e["status"] == s for e in log)
              for s in ("correct", "unchanged", "refused", "missing")}
    print(f"db={db}  protected={protected}  applied={bool(args.apply)}")
    print(f"{verb} {counts['correct']} rows; unchanged {counts['unchanged']}, "
          f"refused {counts['refused']}, missing {counts['missing']}")
    for e in log:
        print(f"  [{e['status']}] {e['id']} {e.get('decisions', '')} {e.get('reason', '')}")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "generated_at": now.isoformat(), "applied": bool(args.apply),
            "database": str(db), "rows": log,
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8", newline="")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
