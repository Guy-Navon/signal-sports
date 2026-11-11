"""Export the public demo snapshot (#458): the live consumer feed of profile
``guy`` as static JSON for the read-only demo on Firebase Hosting.

Usage (from the main checkout, the live worker may keep running):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\export_demo_snapshot.py --out frontend\\dist-demo\\demo-data

Options:
    --out DIR        where feed.json and meta.json are written (required)
    --db PATH        SQLite database to read. Default: the sqlite DATABASE_URL
                     (from the environment or backend/.env, relative paths taken
                     from backend/ like the API does), else backend/data/signal_sports.db
    --env-file PATH  settings file loaded like app.main does (override=False).
                     Default: backend/.env
    --allow-empty    write an empty feed instead of exiting 3

The database is opened read-only and never modified, and no usage is recorded.
Exit codes: 0 written; 1 export failed; 2 usage error; 3 the feed is empty
(on the live corpus: the worker stopped and nothing is inside the freshness
window). On 1 and 3 nothing is written, the previous files stay as they were,
and the publish script must not deploy.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def _load_env_file(env_file: pathlib.Path) -> None:
    """Same contract as app.main._load_dotenv: shell values win (override=False)."""
    if not env_file.exists():
        return
    from dotenv import load_dotenv

    load_dotenv(env_file, override=False)


def _resolve_db(explicit: pathlib.Path | None) -> pathlib.Path:
    if explicit is not None:
        return explicit.resolve()
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("sqlite:///"):
        path = pathlib.Path(url[len("sqlite:///"):])
        return (path if path.is_absolute() else BACKEND / path).resolve()
    return (BACKEND / "data" / "signal_sports.db").resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--db", type=pathlib.Path)
    parser.add_argument("--env-file", type=pathlib.Path, default=BACKEND / ".env")
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args(argv)

    _load_env_file(args.env_file)
    db_path = _resolve_db(args.db)

    # DEPLOY_ENV=dev must not open the production corpus (#265), here as anywhere.
    from app.core.deploy_mode import UnsafeDeployConfig, assert_database_allowed

    try:
        assert_database_allowed(f"sqlite:///{db_path}")
    except UnsafeDeployConfig as exc:
        print(f"EXPORT FAILED: {exc}", file=sys.stderr)
        return 1
    # app.db.database builds a module-level engine from DATABASE_URL at import.
    # The exporter never uses it, but point it at a read-only URI anyway, so an
    # unexpected use fails loudly instead of creating or writing a file.
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_uri()}?mode=ro&uri=true"

    from app.ops.demo_snapshot import EmptyFeedError, ExportError, export_snapshot

    try:
        meta = export_snapshot(db_path, args.out, allow_empty=args.allow_empty)
    except EmptyFeedError as exc:
        print(f"EXPORT SKIPPED: {exc}", file=sys.stderr)
        return 3
    except ExportError as exc:
        print(f"EXPORT FAILED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — any failure must stop the publish
        print(f"EXPORT FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    feed_bytes = (args.out / "feed.json").stat().st_size
    print(f"demo snapshot written to {args.out.resolve()}: {meta['item_count']} items, "
          f"feed.json {feed_bytes} bytes, last cycle {meta['last_successful_cycle_at']}, "
          f"generated {meta['generated_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
