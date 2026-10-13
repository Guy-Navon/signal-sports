"""Verify a database FILE before it is trusted: a backup, a restore candidate,
a copied corpus at the cutover, or a dev snapshot (#266, #269, #270).

    python scripts/verify_db.py <file.db>
    python scripts/verify_db.py <file.db> --expect <other.manifest.json>   # counts and sha256 must match
    python scripts/verify_db.py <file.db> --json

Checks integrity_check, foreign_key_check and that core tables exist, and
prints per-table row counts. Opens the file read-only and immutable: it never
creates -wal/-shm files, so it is safe on a read-only mount. Use it only on a
file no process is writing (a live WAL database would be read without its WAL).

Exit codes: 0 healthy (and matching, with --expect); 1 not; 2 usage.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.ops.sqlite_tools import (  # noqa: E402
    VerificationError,
    compare_counts,
    require_healthy,
    verify_database,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=pathlib.Path)
    parser.add_argument("--expect", type=pathlib.Path, help="a manifest whose sha256 and counts must match")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    problems: list[str] = []
    try:
        report = verify_database(args.file)
        require_healthy(report, required_tables=("articles", "users", "profiles"))
    except VerificationError as exc:
        print(f"NOT OK: {exc}")
        return 1
    if args.expect:
        expected = json.loads(args.expect.read_text(encoding="utf-8"))
        if expected.get("sha256") and expected["sha256"] != report["sha256"]:
            problems.append(f"sha256 differs: expected {expected['sha256']}, got {report['sha256']}")
        problems += compare_counts(expected.get("counts", {}), report["counts"])

    if args.json:
        print(json.dumps({**report, "problems": problems}, indent=2, sort_keys=True))
    else:
        print(f"{args.file}: integrity=ok foreign_keys=ok sha256={report['sha256']} bytes={report['bytes']}")
        for table, count in report["counts"].items():
            print(f"  {table:32} {count}")
        for line in problems:
            print(f"MISMATCH: {line}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
