"""Results feature configuration (issue #178).

Env-driven, read at call time (dotenv is loaded in app.main before imports).
Feature flags follow the project convention: default OFF for anything that
touches the network / scheduler (``.env.example`` stays conservative, the live
``.env`` opts in — the CLUSTERING_ENABLED pattern). The read API (GET) is NOT
network-gated: it always serves whatever is already in the DB.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int = 0) -> int:
    try:
        v = int(os.environ.get(name, str(default)))
        return v if v >= minimum else default
    except (ValueError, TypeError):
        return default


# ── Feature gates ─────────────────────────────────────────────────────────────

def results_enabled() -> bool:
    """Whether the Results surface is offered at all (nav + API). Default ON:
    the read path only reads the DB and is safe with an empty corpus."""
    return _bool("RESULTS_ENABLED", True)


def sync_enabled() -> bool:
    """Whether the scheduler runs the results-sync stage. Default OFF (network
    activity is an ops opt-in, like CLUSTERING/TELEGRAM)."""
    return _bool("RESULTS_SYNC_ENABLED", False)


# ── Provider ──────────────────────────────────────────────────────────────────

def provider_name() -> str:
    return os.environ.get("RESULTS_PROVIDER", "thesportsdb").strip().lower()


def thesportsdb_key() -> str:
    # "3" is TheSportsDB's documented PUBLIC test key — not a secret.
    return os.environ.get("THESPORTSDB_API_KEY", "3").strip() or "3"


def thesportsdb_base_url() -> str:
    return os.environ.get(
        "THESPORTSDB_BASE_URL", "https://www.thesportsdb.com/api/v1/json"
    ).rstrip("/")


def http_timeout_seconds() -> float:
    return float(_int("RESULTS_HTTP_TIMEOUT_SECONDS", 15, minimum=1))


def http_max_retries() -> int:
    return _int("RESULTS_HTTP_MAX_RETRIES", 2, minimum=0)


# ── Scope ─────────────────────────────────────────────────────────────────────

_DEFAULT_COMPETITIONS = (
    # Basketball (Israeli + top European + continental cups)
    "comp:nba",
    "comp:euroleague",
    "comp:eurocup",
    "comp:ibl",
    "comp:acb",
    # Football (the same shape: Israeli + top European leagues + continental cup)
    "comp:ligat_haal",
    "comp:epl",
    "comp:la_liga",
    "comp:bundesliga",
    "comp:ucl",
)


def tracked_competitions() -> list[str]:
    """Competition ids to sync. Product/config decision (NOT per-user). Only
    competitions the active provider knows are actually fetched."""
    raw = os.environ.get("RESULTS_COMPETITIONS")
    if not raw:
        return list(_DEFAULT_COMPETITIONS)
    return [c.strip() for c in raw.split(",") if c.strip()]


def default_seasons(now: datetime | None = None) -> list[str]:
    """The two most recent season labels ("YYYY-YYYY"). Both sports we track run
    roughly Aug/Oct–May/Jun, so before ~August the current-year season is the
    just-finished one. Bounded on purpose — we never crawl full historical
    archives."""
    now = now or datetime.now(tz=timezone.utc)
    y, m = now.year, now.month
    if m >= 8:
        newest = (y, y + 1)
    else:
        newest = (y - 1, y)
    prev = (newest[0] - 1, newest[1] - 1)
    return [f"{newest[0]}-{newest[1]}", f"{prev[0]}-{prev[1]}"]


def seasons() -> list[str]:
    raw = os.environ.get("RESULTS_SEASONS")
    if not raw:
        return default_seasons()
    return [s.strip() for s in raw.split(",") if s.strip()]


def sync_min_interval_seconds() -> int:
    """Throttle: the scheduler stage skips if the last attempt is newer than
    this. Manual admin sync bypasses it (force)."""
    return _int("RESULTS_SYNC_MIN_INTERVAL_SECONDS", 1800, minimum=0)


def max_games_per_competition() -> int:
    return _int("RESULTS_MAX_GAMES_PER_COMPETITION", 80, minimum=1)


# ── Read-path window ──────────────────────────────────────────────────────────

def read_window_days() -> int:
    """How far back the personalized read path looks. Bounded recent history;
    the frontend can page older date-groups client-side within this window."""
    return _int("RESULTS_WINDOW_DAYS", 400, minimum=1)
