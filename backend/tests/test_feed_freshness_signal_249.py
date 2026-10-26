"""#249 — the consumer feed's freshness signal.

``GET /api/me/feed/freshness`` tells a signed-in reader when the feed was last
refreshed and whether automatic ingestion is running, so "nothing happened in
sports" can be told apart from "Signal stopped". It must expose exactly two
fields, and its verdicts must come from the same code as the admin
``/api/scheduler/health`` route: there is no second definition of "running".
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text


def _now():
    return datetime.now(tz=timezone.utc)


@pytest.fixture
def session(client):
    from app.db.database import SessionLocal, init_db
    init_db()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM scheduler_cycles"))
        s.execute(text("DELETE FROM worker_status"))
        s.commit()
        yield s
        s.rollback()
        s.execute(text("DELETE FROM scheduler_cycles"))
        s.execute(text("DELETE FROM worker_status"))
        s.commit()


def _seed_cycle(session, cid, status, minutes_ago):
    from app.db.orm_models import SchedulerCycleRow
    ts = (_now() - timedelta(minutes=minutes_ago)).isoformat()
    session.add(SchedulerCycleRow(
        id=cid, trigger="scheduled", requested_at=ts, started_at=ts,
        finished_at=ts, status=status,
    ))
    session.commit()
    return ts


def _seed_worker(session, state, seconds_ago):
    session.execute(text(
        "INSERT INTO worker_status (id, last_seen_at, state, owner, interval_seconds) "
        "VALUES (1, :t, :s, 'pid=1 host=t', 300)"),
        {"t": (_now() - timedelta(seconds=seconds_ago)).isoformat(), "s": state})
    session.commit()


def test_anonymous_gets_401(client):
    assert client.get("/api/me/feed/freshness").status_code == 401


def test_running_worker_and_last_success(user_client, session):
    _seed_worker(session, "idle", seconds_ago=5)
    _seed_cycle(session, "cycle_old_ok", "succeeded", minutes_ago=30)
    newest_ok = _seed_cycle(session, "cycle_new_ok", "succeeded_with_warnings", minutes_ago=4)
    _seed_cycle(session, "cycle_failed", "failed", minutes_ago=1)

    r = user_client.get("/api/me/feed/freshness")

    assert r.status_code == 200
    body = r.json()
    # Exactly the two fields: nothing else from the admin payload leaks.
    assert set(body) == {"last_successful_cycle_at", "worker_running"}
    assert body["worker_running"] is True
    # The newest SUCCESSFUL cycle, not the newest attempt (which failed).
    assert body["last_successful_cycle_at"] == newest_ok


def test_stale_heartbeat_reads_as_not_running(user_client, session):
    # A crashed worker leaves an "idle" row behind; its heartbeat goes cold.
    _seed_worker(session, "idle", seconds_ago=6 * 3600)
    _seed_cycle(session, "cycle_ok", "succeeded", minutes_ago=6 * 60)

    body = user_client.get("/api/me/feed/freshness").json()

    assert body["worker_running"] is False
    assert body["last_successful_cycle_at"] is not None


def test_no_worker_and_no_cycle_ever(user_client, session):
    body = user_client.get("/api/me/feed/freshness").json()
    assert body == {"last_successful_cycle_at": None, "worker_running": False}


@pytest.mark.parametrize("worker", [
    None,                    # never started
    ("idle", 5),             # healthy
    ("idle", 6 * 3600),      # crashed: stale idle row
    ("stopped", 5),          # stopped cleanly
    ("starting", 5),
])
def test_verdicts_match_the_admin_health_route(user_client, admin_client, session, worker):
    """Same answers as /api/scheduler/health for every worker state."""
    if worker:
        _seed_worker(session, *worker)
    _seed_cycle(session, "cycle_ok", "succeeded", minutes_ago=12)
    _seed_cycle(session, "cycle_bad", "failed", minutes_ago=2)

    mine = user_client.get("/api/me/feed/freshness").json()
    health = admin_client.get("/api/scheduler/health").json()

    assert mine["worker_running"] == health["worker_running"]
    assert mine["last_successful_cycle_at"] == health["last_successful_cycle"]["finished_at"]
