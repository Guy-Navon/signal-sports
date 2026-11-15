"""Results feature configuration (issue #178).

Env-driven, read at call time (dotenv is loaded in app.main before imports).
Feature flags follow the project convention: default OFF for anything that
touches the network / scheduler (``.env.example`` stays conservative, the live
``.env`` opts in — the CLUSTERING_ENABLED pattern). The read API (GET) is NOT
network-gated: it always serves whatever is already in the DB.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone


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


def detail_enabled() -> bool:
    """Whether the sync also fetches per-game detail for finished games (#517).
    Default OFF: with it off the sync sends exactly the requests it sent before."""
    return _bool("RESULTS_DETAIL_ENABLED", False)


def detail_max_per_run() -> int:
    """At most this many games' detail are requested per sync, newest first, so a
    backfill of old games cannot flood a source. 0 = no detail requests."""
    return _int("RESULTS_DETAIL_MAX_PER_RUN", 10, minimum=0)


# ── Provider ──────────────────────────────────────────────────────────────────

def provider_name() -> str:
    return os.environ.get("RESULTS_PROVIDER", "thesportsdb").strip().lower()


def provider_routes_raw() -> str:
    """``RESULTS_PROVIDER_ROUTES``: ``"comp:ibl=winner,comp:euroleague=euroleague"``.
    Empty (default) = every competition goes to ``RESULTS_PROVIDER``. Parsed and
    validated in ``app.results.providers``."""
    return os.environ.get("RESULTS_PROVIDER_ROUTES", "").strip()


def provider_disabled_raw() -> str:
    """``RESULTS_PROVIDER_DISABLED``: comma-separated provider names to switch off
    (#522). A disabled provider is never called; its routed competitions are
    synced and read through ``RESULTS_PROVIDER``. Empty (default) = none."""
    return os.environ.get("RESULTS_PROVIDER_DISABLED", "").strip()


def provider_stale_hours() -> int:
    """``RESULTS_PROVIDER_STALE_HOURS`` (#522, default 6): a routed competition
    whose provider has not succeeded for it within this many hours is read from
    the default provider. 0 turns the staleness fallback off."""
    return _int("RESULTS_PROVIDER_STALE_HOURS", 6, minimum=0)


def provider_backup_sync_enabled() -> bool:
    """``RESULTS_PROVIDER_BACKUP_SYNC`` (#522, default on): with routes set, the
    default provider also fetches the routed competitions so the read-time
    fallback has fresh rows. No effect without routes."""
    return _bool("RESULTS_PROVIDER_BACKUP_SYNC", True)


def thesportsdb_key() -> str:
    # "123" is TheSportsDB's documented PUBLIC test key — not a secret. The old
    # "3" was permanently disabled (403) by October 2026.
    return os.environ.get("THESPORTSDB_API_KEY", "123").strip() or "123"


def thesportsdb_base_url() -> str:
    return os.environ.get(
        "THESPORTSDB_BASE_URL", "https://www.thesportsdb.com/api/v1/json"
    ).rstrip("/")


def http_timeout_seconds() -> float:
    return float(_int("RESULTS_HTTP_TIMEOUT_SECONDS", 15, minimum=1))


def http_min_interval_seconds() -> float:
    """Gap between provider requests. A conservative default, not a verified
    limit: the docs say 30 a minute, yet 2.5 s spacing was blocked at about the
    11th request (2026-10-25). A 20-request sync takes about 2.5 minutes."""
    try:
        v = float(os.environ.get("RESULTS_HTTP_MIN_INTERVAL_SECONDS", "7"))
        return v if v >= 0 else 7.0
    except ValueError:
        return 7.0


def winner_min_interval_seconds() -> float:
    """Gap between requests to the Ligat Winner sources (basket.co.il and Segev,
    #518). Those are the league's own public endpoints with no published limit, so
    the spacing is a courtesy, much shorter than TheSportsDB's."""
    try:
        v = float(os.environ.get("RESULTS_WINNER_MIN_INTERVAL_SECONDS", "2"))
        return v if v >= 0 else 2.0
    except ValueError:
        return 2.0


def bamboo_min_interval_seconds() -> float:
    """Courtesy pacing for all Bamboo football requests (#521), including retries."""
    try:
        v = float(os.environ.get("RESULTS_BAMBOO_MIN_INTERVAL_SECONDS", "2"))
        return v if v >= 0 and v < float("inf") else 2.0
    except ValueError:
        return 2.0


def http_max_retries() -> int:
    return _int("RESULTS_HTTP_MAX_RETRIES", 2, minimum=0)


def espn_min_interval_seconds() -> float:
    """Courtesy spacing for the undocumented ESPN NBA endpoints (#520)."""
    try:
        value = float(os.environ.get("RESULTS_ESPN_MIN_INTERVAL_SECONDS", "2"))
        return value if 0 <= value < float("inf") else 2.0
    except ValueError:
        return 2.0


def espn_days_back() -> int:
    """US scoreboard dates before today; bounded to two weeks."""
    return min(_int("RESULTS_ESPN_DAYS_BACK", 1), 14)


def espn_days_ahead() -> int:
    """US scoreboard dates after today; bounded to a week."""
    return min(_int("RESULTS_ESPN_DAYS_AHEAD", 3), 7)


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


def recent_days() -> int:
    """How many UTC days (today first) to ask ``eventsday`` for, per league.
    Each day is one request per competition; 0 (the default) turns the per-day fetch off,
    so deploying the code adds no provider traffic until the owner sets it in .env.
    Capped at a week so a config typo cannot multiply the requests."""
    return min(_int("RESULTS_RECENT_DAYS", 0, minimum=0), 7)


def recent_dates(now: datetime, days: int) -> list[str]:
    """``days`` UTC dates ("YYYY-MM-DD"), newest first, ending at ``now``."""
    today = now.astimezone(timezone.utc).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(days)]


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
