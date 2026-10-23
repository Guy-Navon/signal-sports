"""Protect every N05- and census-rated article from retention cleanup (#255).

One-off and idempotent: reads the rating and sample documents in docs/qa and
adds their article ids to `protected_articles`. New censuses protect themselves
(`rate_census.py build`), so this only backfills what existed before #255.

Dry run by default. Back up first, then apply:
    .venv\\Scripts\\python.exe scripts/backup_db.py
    .venv\\Scripts\\python.exe scripts/protect_rated_articles.py            # dry run
    .venv\\Scripts\\python.exe scripts/protect_rated_articles.py --apply

The database is DATABASE_URL (from the environment or backend/.env), as for the
API and the worker. Existing rows keep their first reason.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from app.qa import census_rating as cr  # noqa: E402

QA_DIR = _BACKEND.parent / "docs" / "qa"
PATTERNS = ("n05_ratings.json", "n05_sample.json", "census*_ratings.json", "census*_sample.json")


def documents(qa_dir: Path) -> list[Path]:
    return sorted({path for pattern in PATTERNS for path in qa_dir.glob(pattern)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--qa-dir", type=Path, default=QA_DIR)
    parser.add_argument("--apply", action="store_true", help="write; without it nothing is written")
    args = parser.parse_args(argv)

    try:
        from dotenv import load_dotenv

        load_dotenv(_BACKEND / ".env", override=False)
    except ImportError:  # pragma: no cover
        pass
    from sqlalchemy import text

    from app.core.config import settings
    from app.db.database import SessionLocal, init_db
    from app.repositories import protected_article_repository

    docs = documents(args.qa_dir)
    if not docs:
        print(f"no rating or sample documents in {args.qa_dir}")
        return 2
    print(f"database: {settings.database_url}  ({'APPLY' if args.apply else 'dry run'})")
    if args.apply:
        init_db()  # creates protected_articles on a pre-#255 database

    with SessionLocal() as session:
        existing = {r[0] for r in session.execute(text("SELECT id FROM articles"))}
        total_added = 0
        for path in docs:
            ids = cr.article_ids(json.loads(path.read_text(encoding="utf-8")))
            in_db = len(ids & existing)
            if args.apply:
                added = protected_article_repository.protect(session, ids, reason=path.stem)
            else:
                added = len(ids)  # upper bound: a dry run may run before the table exists
            total_added += added
            print(f"{path.name}: {len(ids)} ids, {in_db} in the corpus, "
                  f"{'added' if args.apply else 'would add up to'} {added}")
        if args.apply:
            session.commit()
    print(f"{'added' if args.apply else 'would add up to'} {total_added} protection rows (overlaps counted once when applied)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
