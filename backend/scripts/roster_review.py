"""Read-only review aid for the #259 club-people roster (``implies_team``), issue #377.

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts/roster_review.py
        List every implies_team person by club, with aliases, next to the official roster page.

    .venv\\Scripts\\python.exe scripts/roster_review.py --db <copy.db> NAME [NAME ...]
        For the alias-safety check: print every corpus title/subtitle that mentions NAME the
        way the resolver matches a club-person alias (any geresh spelling, hyphens folded, a
        standalone word: "מדריד" is not "מדר"), and count the raw substring hits beside it.
        The week-sample holdout rows (split "test") are skipped, as in the #259 selection.

Changes nothing: the registry is read from code and the database is opened read-only. --db
must be a verified COPY made with scripts/backup_db.py. A file named signal_sports.db, or one
with a -wal/-shm sidecar (a live WAL database; backup copies use journal_mode=DELETE), is
refused.
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
from app.taxonomy.resolver import (  # noqa: E402
    _find_occurrences,
    _is_standalone_word,
    normalize_alias_text,
)

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
    """Week-sample holdout ids; an empty set (with a note) once the sample file is retired."""
    if not path.exists():
        print(f"note: {path.name} not found, so no holdout rows are skipped")
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["id"] for profile in data["profiles"].values()
            for item in profile["items"] if item["split"] == "test"}


def _resolver_match(text: str, variants: list[str]) -> bool:
    """True when ``text`` names one of ``variants`` the way the resolver matches a
    word-bounded alias (every club-person alias is one): hyphens folded, and the hit a
    standalone word (prefix chain allowed, no Hebrew letter or geresh after it)."""
    norm = normalize_alias_text(text)
    return any(_is_standalone_word(norm, span)
               for v in variants for span in _find_occurrences(norm, v))


def find_mentions(db: Path, name: str, skip_ids: set[str]) -> tuple[list[tuple], int]:
    """Corpus rows that mention ``name`` as the resolver would match it, plus the number
    of rows that merely contain it as a raw substring (hits inside longer words included).

    SQL prefilters on every word of each geresh spelling (a superset that still finds
    hyphenated text); the match itself is decided in Python with the resolver's helpers."""
    variants = [normalize_alias_text(v) for v in _geresh_variants(name)]
    clauses, params = [], []
    for v in variants:
        words = v.split()
        clauses.append("(" + " AND ".join(
            "(instr(lower(title), ?) > 0 OR instr(lower(coalesce(subtitle, '')), ?) > 0)"
            for _ in words) + ")")
        params += [w for w in words for _ in (0, 1)]
    con = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute(
            f"SELECT id, published_at, source, title, coalesce(subtitle, '') FROM articles "
            f"WHERE {' OR '.join(clauses)} ORDER BY published_at", params,
        ).fetchall()
    finally:
        con.close()
    rows = [r for r in rows if r[0] not in skip_ids]
    raw = sum(1 for r in rows if any(v in f"{r[3]}\n{r[4]}".lower() for v in variants))
    matched = [r[1:] for r in rows
               if _resolver_match(r[3], variants) or _resolver_match(r[4], variants)]
    return matched, raw


def _looks_live(db: Path) -> bool:
    """The live corpus, wherever the script runs from: this checkout's file, any file
    with its name, or a database in WAL mode (it has -wal/-shm sidecars)."""
    if db.resolve() == LIVE_DB.resolve() or db.name.lower() == LIVE_DB.name:
        return True
    return any(db.with_name(db.name + suffix).exists() for suffix in ("-wal", "-shm"))


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
    if _looks_live(args.db):
        print("refusing what looks like a live corpus file (signal_sports.db, or a -wal/-shm "
              "sidecar): make a copy with scripts/backup_db.py first")
        return 2
    skip = holdout_ids()
    for name in args.names:
        rows, raw = find_mentions(args.db, name, skip)
        print(f"\n{name}: {len(rows)} mention(s) as the resolver matches it, "
              f"{raw} raw substring hit(s) (inside longer words too); holdout skipped")
        for published_at, source, title, subtitle in rows:
            print(f"  {published_at[:10]} | {source} | {title} | {subtitle[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
