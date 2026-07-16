"""Checkpointed SQLite backup (#155). With WAL journal mode, the newest writes
may live in the -wal sidecar — a bare file copy can be behind. This uses the
sqlite3 backup API, which produces a consistent snapshot regardless of journal
mode, then verifies row counts.

Usage:
    .venv\\Scripts\\python.exe scripts/backup_db.py [dest-path]
Default destination: data/backups/backup_<UTC timestamp>.db
"""
from __future__ import annotations

import pathlib
import sqlite3
import sys
from datetime import datetime, timezone


def main() -> int:
    backend = pathlib.Path(__file__).resolve().parents[1]
    src = backend / "data" / "signal_sports.db"
    if not src.exists():
        print(f"source not found: {src}")
        return 1
    if len(sys.argv) > 1:
        dest = pathlib.Path(sys.argv[1])
    else:
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = backend / "data" / "backups" / f"backup_{stamp}.db"
    dest.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(src) as source, sqlite3.connect(dest) as target:
        source.backup(target)

    a = sqlite3.connect(f"file:{src}?mode=ro", uri=True).execute(
        "SELECT COUNT(*) FROM articles").fetchone()[0]
    b = sqlite3.connect(f"file:{dest}?mode=ro", uri=True).execute(
        "SELECT COUNT(*) FROM articles").fetchone()[0]
    print(f"backup written: {dest}")
    print(f"articles: live={a} backup={b} match={a == b}")
    return 0 if a == b else 1


if __name__ == "__main__":
    raise SystemExit(main())
