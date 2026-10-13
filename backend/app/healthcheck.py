"""
Container health probes (#263).

    python -m app.healthcheck api      # GET http://127.0.0.1:8000/health
    python -m app.healthcheck worker   # is the worker heartbeat fresh?

Exit 0 = healthy, 1 = unhealthy, with one line on stdout saying why. Standard
library only, and the worker probe opens the database **read-only**: a probe
must never run migrations, startup checks or the seeders the app runs.

Worker freshness. The worker writes ``worker_status`` at start and after every
tick, so between ticks the row is at most one interval old. During a cycle it
is not rewritten, but the cycle's lease heartbeat (``scheduler_lease``) is,
every 10 s. The worker is healthy when either is fresh:

- ``worker_status`` is ``starting`` or ``idle`` and younger than
  interval + SCHEDULER_MAX_RUN_SECONDS + 120 s of slack, or
- the lease is held and its heartbeat is younger than 120 s.

A ``stopped`` row is unhealthy: the process said it was exiting.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Optional

_LEASE_FRESH_SECONDS = 120
_SLACK_SECONDS = 120


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
        return value if value >= 1 else default
    except ValueError:
        return default


def _age_seconds(iso: Optional[str], now: datetime) -> Optional[float]:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (now - then).total_seconds()


def _sqlite_path(url: str) -> Optional[str]:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    return url[len(prefix):] or None


def check_api(url: str = "http://127.0.0.1:8000/health", timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - fixed local URL
            body = response.read(200).decode("utf-8", "replace")
            if response.status == 200 and '"ok"' in body:
                return True, "api ok"
            return False, f"api answered {response.status}"
    except Exception as exc:  # noqa: BLE001 - any failure is "unhealthy"
        return False, f"api unreachable: {type(exc).__name__}"


def check_worker(database_url: str, now: Optional[datetime] = None) -> tuple[bool, str]:
    now = now or datetime.now(tz=timezone.utc)
    path = _sqlite_path(database_url)
    if path is None:
        return False, "worker check needs a sqlite DATABASE_URL"
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as exc:
        return False, f"database not readable: {type(exc).__name__}"
    try:
        status = conn.execute(
            "SELECT state, last_seen_at, interval_seconds FROM worker_status WHERE id = 1"
        ).fetchone()
        lease = conn.execute(
            "SELECT active_cycle_id, heartbeat_at FROM scheduler_lease WHERE id = 1"
        ).fetchone()
    except sqlite3.Error as exc:
        return False, f"heartbeat tables not readable: {type(exc).__name__}"
    finally:
        conn.close()

    if lease and lease[0]:
        age = _age_seconds(lease[1], now)
        if age is not None and age <= _LEASE_FRESH_SECONDS:
            return True, f"cycle running, lease heartbeat {age:.0f}s old"

    if not status:
        return False, "no worker heartbeat yet"
    state, last_seen, interval = status
    if state not in ("starting", "idle"):
        return False, f"worker state is {state!r}"
    age = _age_seconds(last_seen, now)
    if age is None:
        return False, "worker heartbeat has no timestamp"
    limit = (interval or _int_env("SCHEDULER_INTERVAL_SECONDS", 300)) \
        + _int_env("SCHEDULER_MAX_RUN_SECONDS", 900) + _SLACK_SECONDS
    if age > limit:
        return False, f"worker heartbeat {age:.0f}s old (limit {limit}s)"
    return True, f"worker {state}, heartbeat {age:.0f}s old"


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("api", "worker"):
        print("usage: python -m app.healthcheck api|worker")
        return 2
    if argv[1] == "api":
        ok, why = check_api()
    else:
        ok, why = check_worker(os.environ.get("DATABASE_URL", "sqlite:///./data/signal_sports.db"))
    print(why)
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover - process entry
    raise SystemExit(main(sys.argv))
