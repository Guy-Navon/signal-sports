"""Checkpointed SQLite backup (#155, extended for #266). With WAL journal mode,
the newest writes may live in the -wal sidecar, so a bare file copy can be
behind. This uses the sqlite3 backup API (consistent while the API and worker
keep writing), makes the copy one self-contained file, then VERIFIES it:
integrity_check, foreign_key_check and per-table row counts.

Usage (unchanged on the PC):
    .venv\\Scripts\\python.exe scripts/backup_db.py [dest-path]
Default destination: data/backups/backup_<UTC timestamp>.db

Options:
    --src PATH          database to copy (default: data/signal_sports.db; inside
                        the image that is /app/data/signal_sports.db)
    --manifest          also write <dest>.manifest.json (sha256, size, counts)
    --expect-quiescent  every writer is stopped (the cutover): the copy's counts
                        must equal the source's exactly, or exit 1

Exit codes: 0 verified; 1 verification failed (do not use the file); 2 usage.
The source is opened read-only and never modified.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.ops.sqlite_tools import (  # noqa: E402
    VerificationError,
    backup_copy,
    compare_counts,
    write_manifest,
)


def main(argv: list[str] | None = None) -> int:
    backend = pathlib.Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dest", nargs="?", type=pathlib.Path)
    parser.add_argument("--src", type=pathlib.Path, default=backend / "data" / "signal_sports.db")
    parser.add_argument("--manifest", action="store_true")
    parser.add_argument("--expect-quiescent", action="store_true")
    args = parser.parse_args(argv)

    if not args.src.exists():
        print(f"source not found: {args.src}")
        return 1
    dest = args.dest
    if dest is None:
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = backend / "data" / "backups" / f"backup_{stamp}.db"

    try:
        report = backup_copy(args.src, dest)
    except VerificationError as exc:
        print(f"BACKUP FAILED: {exc}")
        return 1

    counts, live = report["counts"], report["source_counts_after"]
    print(f"backup written: {dest}")
    print(f"sha256={report['sha256']} bytes={report['bytes']} integrity=ok foreign_keys=ok")
    print(f"articles: live={live.get('articles')} backup={counts.get('articles')}")
    drift = compare_counts(counts, live)
    if drift:
        if args.expect_quiescent:
            print("BACKUP FAILED: the source changed during a quiescent backup:")
            for line in drift:
                print(f"  {line}")
            return 1
        print("note: the live source moved on after the copy (expected while writers run):")
        for line in drift[:10]:
            print(f"  {line}")
    if args.manifest:
        manifest = write_manifest(report, dest.with_name(dest.name + ".manifest.json"))
        print(f"manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
