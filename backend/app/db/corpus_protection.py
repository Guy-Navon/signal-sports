"""
Corpus DB protection (issue #106).

The real article corpus (``backend/data/signal_sports.db``) is irreplaceable: it
is the substrate for every decision-drift baseline, golden case, and real-data QA
run in this repo. It is NOT in git (``.gitignore``: ``backend/data/``), so a
destructive mistake against it is unrecoverable.

On 2026-07-12 it was reset from 404 RSS articles to 0 by a dev endpoint. The only
protection at the time was a single boolean (``ALLOW_DEV_RESET``), which was
``true`` in ``backend/.env`` while ``DATABASE_URL`` pointed at the corpus. A
boolean is not a guard — flipping it back re-arms the hazard.

This module guards the **target database** instead of a flag: destructive dev
routes ask whether the *currently active* DB is the canonical corpus file, and
refuse accordingly. In particular the LLM gating benchmark resets RSS data twice
per run **by design**, which is why it must never be pointed at the corpus (this
is the landmine that would have fired on issue #65).

Contract:
- ``is_protected_corpus_db()`` — True when the active SQLAlchemy URL resolves to
  the canonical corpus file, regardless of how the URL was spelled (relative,
  absolute, forward/back slashes).
- Benchmarks: **hard refusal** on the corpus, with no override. Run them against
  a copy (``DATABASE_URL=sqlite:///./data/benchmark_copy.db``).
- Corpus reset: allowed only with a SECOND, corpus-specific opt-in
  (``ALLOW_CORPUS_DB_RESET=true``) on top of ``ALLOW_DEV_RESET``.
"""

import os
from pathlib import Path
from typing import Optional

# The canonical corpus file, relative to the backend package root.
# backend/app/db/corpus_protection.py → parents[2] == backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_CORPUS_PATH = (_BACKEND_ROOT / "data" / "signal_sports.db").resolve()

_SQLITE_PREFIX = "sqlite:///"


def _sqlite_path_from_url(url: str) -> Optional[Path]:
    """Resolve a sqlite SQLAlchemy URL to an absolute filesystem path.

    Returns None for non-sqlite URLs and for in-memory databases (which are never
    the corpus). Relative paths resolve against the backend root — that is how
    ``sqlite:///./data/signal_sports.db`` is written in ``backend/.env``.
    """
    if not url.startswith(_SQLITE_PREFIX):
        return None

    raw = url[len(_SQLITE_PREFIX):]
    if not raw or ":memory:" in raw:
        return None

    path = Path(raw)
    if not path.is_absolute():
        path = _BACKEND_ROOT / path

    try:
        return path.resolve()
    except OSError:  # pragma: no cover — unresolvable path is, by definition, not the corpus
        return None


def active_database_url() -> str:
    """The DB URL the app is actually using (env first, matching app.db.database)."""
    return os.environ.get("DATABASE_URL", "")


def is_protected_corpus_db(url: Optional[str] = None) -> bool:
    """True when the active database is the canonical article corpus."""
    resolved = _sqlite_path_from_url(url if url is not None else active_database_url())
    return resolved is not None and resolved == CANONICAL_CORPUS_PATH


def corpus_reset_opt_in() -> bool:
    """The SECOND, corpus-specific opt-in required to reset the real corpus.

    Deliberately separate from ALLOW_DEV_RESET: resetting a scratch DB and
    destroying the corpus are different decisions and must not share one switch.
    """
    return os.environ.get("ALLOW_CORPUS_DB_RESET", "false").lower() == "true"
