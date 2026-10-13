"""Make a SANITIZED dev snapshot of a database (HOSTING_PLAN §12.3, #270).

    python scripts/make_dev_snapshot.py --src <corpus.db> --out <snapshot.db> [--manifest]

Works on a copy (the backup API, source opened read-only); the source is never
modified. Removes sessions, credentials and personal fields, keeps every id
and relation (profiles, feedback, calibration, notifications, articles,
clusters), rebuilds the file with VACUUM INTO, and verifies it: integrity,
foreign keys, unchanged counts outside the cleared tables, no email outside
@example.invalid, no password hash, and no original email or machine name
anywhere in the file's bytes.

The snapshot is for development and read-only QA (the N05 gate, the census
tools). It is NOT a backup: never restore it as the production corpus. On the
host it is encrypted to the separate DEV key (deploy/devsnap.sh); dev never
receives a key that decrypts a full backup.

Exit codes: 0 verified snapshot written; 1 failed (no file is left); 2 usage.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.ops.sqlite_tools import VerificationError, make_dev_snapshot, write_manifest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--src", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", action="store_true")
    args = parser.parse_args(argv)
    if args.src.resolve() == args.out.resolve():
        parser.error("--out must differ from --src")
    try:
        report = make_dev_snapshot(args.src, args.out)
    except VerificationError as exc:
        print(f"SNAPSHOT FAILED: {exc}")
        return 1
    print(f"dev snapshot written: {args.out}")
    print(f"sha256={report['sha256']} bytes={report['bytes']} emails_rewritten={report['emails_rewritten']}")
    print(f"cleared: {', '.join(report['cleared_tables'])}; articles={report['counts'].get('articles')}")
    if args.manifest:
        print(f"manifest: {write_manifest(report, args.out.with_name(args.out.name + '.manifest.json'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
