"""Protect every human-rated, sampled or hand-corrected article from retention cleanup (#255).

Idempotent backfill: reads the rating, sample and correction-log documents in
docs/qa and adds their article ids to `protected_articles`. `rate_census.py
build` protects each new census itself; this covers every other set, before and
after #255.

Which files count, by name (no list to keep up to date):
    *_ratings.json            ratings stores (N05, censuses, re-rates, week sample, ...)
    *_sample.json             samples, rated or still being rated
    <name>.json               a sample saved beside its <name>_ratings.json
Only the top level of docs/qa is read. tests/test_protect_rated_articles_255.py
fails if a file anywhere under docs/qa in one of the two formats the rating
tooling writes (a ratings store or a sample) is not covered. A covered file
that names no article id stops the run before any write, unless it is a ratings
store still waiting for its first rating.

Correction logs, a third format ({"rows": [{"id": ...}]}), are an explicit list,
CORRECTION_LOGS below (owner decision 2026-11-02): their rows are articles whose
stored facts were corrected by a reviewed apply script, the evidence of those fixes.
The test fails if a *_corrections.json or *_log.json in docs/qa is not listed.
Score and analysis output are not protected.

Ratings documents are read first, in natural order (census_, census2_, census10_),
so an id's reason names the first document that RATED it; a sample is the reason
only for ids nobody has rated yet, and a correction log only for ids that were
corrected but never rated or sampled.

Dry run by default; it reports the exact rows an apply would add, the rated or
sampled ids that are still unprotected, and retention's own dry-run summary
(nothing is written or deleted). On the live corpus, back up first:
    .venv\\Scripts\\python.exe scripts/backup_db.py
    .venv\\Scripts\\python.exe scripts/protect_rated_articles.py            # dry run
    .venv\\Scripts\\python.exe scripts/protect_rated_articles.py --apply --i-know-this-is-the-live-corpus

The database is DATABASE_URL (from the environment or backend/.env), as for the
API and the worker. Existing rows keep their first reason.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from app.qa import census_rating as cr  # noqa: E402

QA_DIR = _BACKEND.parent / "docs" / "qa"
_RATINGS = "_ratings.json"
_SAMPLE = "_sample.json"

# Applied correction logs: file -> why its articles are kept (documentation; the
# reason stored per id is the file stem, as for ratings and samples).
CORRECTION_LOGS = {
    # N05 ground-truth pass: stored entity attribution corrected where a club was
    # named only as a former affiliation ("אקס מכבי ת"א"); applied 2026-09-06.
    "n05_former_affiliation_log.json": "former-affiliation entity corrections (N05)",
    # #190 Israeli-basketball recall: missing club entities added by title evidence; 2026-09-11.
    "n190_entity_corrections.json": "Israeli-basketball entity corrections (#190)",
    # #191 event-type corrections from a reviewed dry run; still a regression set
    # (docs/qa/N05_FEED_QUALITY_IMPLEMENTATION.md, signal-quality-eval).
    "n191_event_corrections.json": "event-type corrections, regression set (#191)",
}


def _prefix(path: Path) -> str:
    for suffix in (_RATINGS, _SAMPLE, ".json"):
        if path.name.endswith(suffix):
            return path.name[: -len(suffix)]
    return path.name


def _natural(path: Path) -> list:
    # re.split with a group alternates text and digits, so equal positions hold equal types.
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", _prefix(path))]


def documents(qa_dir: Path) -> list[Path]:
    """Ratings documents, then samples; each group in natural prefix order, so
    census_* comes before census2_* and census10_*."""
    ratings = sorted(qa_dir.glob("*" + _RATINGS), key=_natural)
    samples = set(qa_dir.glob("*" + _SAMPLE))
    samples |= {qa_dir / f"{_prefix(r)}.json" for r in ratings if (qa_dir / f"{_prefix(r)}.json").exists()}
    return ratings + sorted(samples, key=_natural)


def correction_log_ids(doc) -> set[str]:
    """The article ids of an applied correction log: one row per corrected article."""
    rows = doc.get("rows") if isinstance(doc, dict) else None
    return {row["id"] for row in rows or [] if isinstance(row, dict) and "id" in row}


def unreadable(doc) -> bool:
    """True when a document names no article id and is not a ratings store still
    waiting for its first rating: its shape is one article_ids() cannot read, so
    applying it would protect nothing."""
    try:
        if cr.article_ids(doc):
            return False
    except (AttributeError, TypeError, KeyError):
        return True
    ratings = doc.get("ratings")
    return not (isinstance(ratings, dict) and all(isinstance(v, dict) for v in ratings.values()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--qa-dir", type=Path, default=QA_DIR)
    parser.add_argument("--apply", action="store_true", help="write; without it nothing is written")
    parser.add_argument("--i-know-this-is-the-live-corpus", action="store_true",
                        help="required for --apply on the live corpus, once scripts/backup_db.py has run")
    args = parser.parse_args(argv)

    try:
        from dotenv import load_dotenv

        load_dotenv(_BACKEND / ".env", override=False)
    except ImportError:  # pragma: no cover
        pass
    from sqlalchemy import inspect, text

    from app.core.config import settings
    from app.db import corpus_protection
    from app.db.database import SessionLocal, engine, init_db
    from app.ingestion.retention import cleanup_articles
    from app.repositories import protected_article_repository

    docs = documents(args.qa_dir)
    if not docs:
        print(f"no rating or sample documents in {args.qa_dir}")
        return 2
    loaded = [(path, json.loads(path.read_text(encoding="utf-8")), cr.article_ids) for path in docs]
    broken = [path.name for path, doc, _ in loaded if unreadable(doc)]
    for name in CORRECTION_LOGS:
        path = args.qa_dir / name
        if not path.exists():
            print(f"{name}: not in {args.qa_dir}, skipped")
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not correction_log_ids(doc):
            broken.append(name)
        loaded.append((path, doc, correction_log_ids))
    if broken:
        print(f"Refusing: these documents name no article id in a shape this script reads: {broken}")
        return 2
    print(f"database: {settings.database_url}  ({'APPLY' if args.apply else 'dry run'})")
    if args.apply and corpus_protection.is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
        print("Refusing: that is the live corpus. Run scripts/backup_db.py first, then re-run with "
              "--apply --i-know-this-is-the-live-corpus.")
        return 2
    if args.apply:
        init_db()  # creates protected_articles on a pre-#255 database
    has_table = inspect(engine).has_table("protected_articles")

    with SessionLocal() as session:
        existing = {r[0] for r in session.execute(text("SELECT id FROM articles"))}
        protected = protected_article_repository.protected_ids(session) if has_table else set()
        named: set[str] = set()
        total_added = 0
        for path, doc, read_ids in loaded:
            ids = read_ids(doc)
            named |= ids
            if args.apply:
                added = protected_article_repository.protect(session, ids, reason=path.stem)
            else:
                added = len(ids - protected)
                protected |= ids
            total_added += added
            print(f"{path.name}: {len(ids)} ids, {len(ids & existing)} in the corpus, "
                  f"{'added' if args.apply else 'would add'} {added}")
        if args.apply:
            session.commit()
        print(f"{'added' if args.apply else 'would add'} {total_added} protection rows "
              f"({len(named)} distinct ids, {len(named & existing)} in the corpus)")

        stored = protected_article_repository.protected_ids(session) if has_table else set()
        print(f"{len((named & existing) - stored)} rated, sampled or corrected ids in the corpus are NOT protected")
        if has_table:
            s = cleanup_articles(session, dry_run=True)  # computes only; never deletes
            print(f"retention dry run ({s['retention_days']} days, cutoff {s['cutoff']}): "
                  f"candidates={s['candidates']} protected_cluster={s['protected_cluster']} "
                  f"protected_feedback={s['protected_feedback']} protected_rated={s['protected_rated']} "
                  f"deletable={s['deleted']}"
                  + (f" ({s['skipped_reason']})" if s.get("skipped_reason") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
