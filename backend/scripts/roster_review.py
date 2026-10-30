"""Read-only review aid for the #259 club-people roster (``implies_team``), issue #377.

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts/roster_review.py
        List every implies_team person by club, with aliases, next to the official roster page.

    .venv\\Scripts\\python.exe scripts/roster_review.py --db <copy.db> NAME [NAME ...]
        Print every corpus title/subtitle containing NAME (a raw substring, the way the resolver
        scans, in all three geresh spellings) for the alias-safety check. The week-sample
        holdout rows (split "test") are skipped, as in the #259 selection.

Changes nothing: the registry is read from code and the database is opened read-only. --db
must be a verified COPY made with scripts/backup_db.py; the live corpus file is refused.
Procedure: docs/TAXONOMY.md, "Roster maintenance".
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.taxonomy import ENTITIES  # noqa: E402
from app.taxonomy.entities import _geresh_variants  # noqa: E402

LIVE_DB = BACKEND / "data" / "signal_sports.db"
WEEK_SAMPLE = BACKEND.parent / "docs" / "qa" / "week_sample_2026-10.json"
ROSTER_PAGES = {
    "team:maccabi_tlv_bb": "https://basket.co.il/team.asp?TeamId=2111&lang=en",
    "team:hapoel_tlv_bb": "https://basket.co.il/team.asp?TeamId=2112&lang=en",
}


def roster_by_club() -> dict[str, list]:
    clubs: dict[str, list] = {}
    for e in ENTITIES.values():
        if e.implies_team:
            clubs.setdefault(e.team_id, []).append(e)
    return {club: sorted(people, key=lambda e: (e.kind, e.display_en))
            for club, people in sorted(clubs.items())}


def holdout_ids(path: Path = WEEK_SAMPLE) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["id"] for profile in data["profiles"].values()
            for item in profile["items"] if item["split"] == "test"}


def find_mentions(db: Path, name: str, skip_ids: set[str]) -> list[tuple]:
    variants = [v.lower() for v in _geresh_variants(name)]
    where = " OR ".join(
        "instr(lower(title), ?) > 0 OR instr(lower(coalesce(subtitle, '')), ?) > 0"
        for _ in variants
    )
    params = [v for v in variants for _ in (0, 1)]
    con = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute(
            f"SELECT id, published_at, source, title, coalesce(subtitle, '') FROM articles "
            f"WHERE {where} ORDER BY published_at", params,
        ).fetchall()
    finally:
        con.close()
    return [r[1:] for r in rows if r[0] not in skip_ids]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, help="a verified copy of the corpus")
    parser.add_argument("names", nargs="*", help="names or aliases to look up (needs --db)")
    args = parser.parse_args(argv)

    if not args.db:
        if args.names:
            parser.error("names need --db <copy.db>")
        for club, people in roster_by_club().items():
            print(f"\n{club}  ({len(people)})  official roster: {ROSTER_PAGES.get(club, '?')}")
            for e in people:
                aliases = ", ".join(a for a in e.aliases if "׳" not in a and "`" not in a)
                print(f"  {e.kind:<6} {e.id:<32} {e.display_en:<20} {aliases}")
        return 0

    if not args.names:
        parser.error("--db needs at least one name")
    if not args.db.exists():
        print(f"database not found: {args.db}")
        return 2
    if args.db.resolve() == LIVE_DB.resolve():
        print("refusing the live corpus file: make a copy with scripts/backup_db.py first")
        return 2
    skip = holdout_ids()
    for name in args.names:
        rows = find_mentions(args.db, name, skip)
        print(f"\n{name}: {len(rows)} mention(s), holdout skipped")
        for published_at, source, title, subtitle in rows:
            print(f"  {published_at[:10]} | {source} | {title} | {subtitle[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
