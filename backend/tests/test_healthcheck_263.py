"""Container health probes (#263): app/healthcheck.py.

The worker probe reads a temp SQLite file read-only; the API probe is pointed
at a closed local port. No network, no app startup.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from app import healthcheck

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def _db(tmp_path, status=None, lease=None):
    path = tmp_path / "hc.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE worker_status (id INTEGER PRIMARY KEY, last_seen_at TEXT, "
                 "state TEXT, owner TEXT, interval_seconds INTEGER)")
    conn.execute("CREATE TABLE scheduler_lease (id INTEGER PRIMARY KEY, active_cycle_id TEXT, "
                 "heartbeat_at TEXT, owner TEXT)")
    if status:
        state, age = status
        conn.execute("INSERT INTO worker_status VALUES (1, ?, ?, 'w', 300)",
                     ((NOW - timedelta(seconds=age)).isoformat(), state))
    if lease:
        cycle, age = lease
        conn.execute("INSERT INTO scheduler_lease VALUES (1, ?, ?, 'w')",
                     (cycle, (NOW - timedelta(seconds=age)).isoformat()))
    conn.commit()
    conn.close()
    return f"sqlite:///{path.as_posix()}"


def test_fresh_idle_worker_is_healthy(tmp_path):
    ok, why = healthcheck.check_worker(_db(tmp_path, status=("idle", 200)), now=NOW)
    assert ok, why


def test_starting_worker_is_healthy(tmp_path):
    assert healthcheck.check_worker(_db(tmp_path, status=("starting", 5)), now=NOW)[0]


def test_stale_worker_is_unhealthy(tmp_path):
    # 300 interval + 900 max run + 120 slack = 1320 s.
    ok, why = healthcheck.check_worker(_db(tmp_path, status=("idle", 1400)), now=NOW)
    assert not ok and "1320" in why


def test_stopped_worker_is_unhealthy(tmp_path):
    ok, why = healthcheck.check_worker(_db(tmp_path, status=("stopped", 1)), now=NOW)
    assert not ok and "stopped" in why


def test_long_cycle_with_fresh_lease_is_healthy(tmp_path):
    url = _db(tmp_path, status=("idle", 1400), lease=("cycle_x", 15))
    ok, why = healthcheck.check_worker(url, now=NOW)
    assert ok and "cycle running" in why


def test_stale_lease_does_not_rescue_a_dead_worker(tmp_path):
    url = _db(tmp_path, status=("idle", 1400), lease=("cycle_x", 600))
    assert not healthcheck.check_worker(url, now=NOW)[0]


def test_no_heartbeat_yet_is_unhealthy(tmp_path):
    assert not healthcheck.check_worker(_db(tmp_path), now=NOW)[0]


def test_missing_database_is_unhealthy_and_not_created(tmp_path):
    missing = tmp_path / "absent.db"
    ok, _ = healthcheck.check_worker(f"sqlite:///{missing.as_posix()}", now=NOW)
    assert not ok
    assert not missing.exists()


def test_non_sqlite_url_is_unhealthy():
    assert not healthcheck.check_worker("postgresql://x/y", now=NOW)[0]


def test_api_probe_reports_unreachable():
    ok, why = healthcheck.check_api("http://127.0.0.1:9/health", timeout=0.5)
    assert not ok and "unreachable" in why


def test_cli_usage():
    assert healthcheck.main(["x"]) == 2
    assert healthcheck.main(["x", "nope"]) == 2
