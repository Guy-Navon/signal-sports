"""M7-2 (#148) — the dedicated scheduler worker.

The loop itself is a plain while over Event.wait; tests exercise the tick, the
catch-up decision, the config contract and the heartbeat — never a real sleep
cadence and never a real source fetch.
"""

import threading
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.worker import (
    SchedulerConfig,
    beat,
    read_scheduler_config,
    run_tick,
    should_catch_up,
    worker_loop,
)

RUN_INGESTION = "app.ingestion.ingestion_service.run_ingestion"


def _cfg(**over) -> SchedulerConfig:
    base = dict(enabled=True, interval_seconds=1, run_on_startup=False,
                startup_catchup=True, max_run_seconds=900,
                stale_after_seconds=1800)
    base.update(over)
    return SchedulerConfig(**base)


def _result():
    return types.SimpleNamespace(
        source_id="walla_sport", fetched=1, inserted=0, skipped_duplicate=1,
        skipped_filtered=0, failed=0, errors=[],
    )


@pytest.fixture
def session(_application):
    from app.db.database import SessionLocal, init_db
    init_db()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM scheduler_cycles"))
        s.execute(text("UPDATE scheduler_lease SET active_cycle_id=NULL, "
                       "heartbeat_at=NULL, owner=NULL WHERE id=1"))
        s.commit()
        yield s
        s.rollback()
        s.execute(text("DELETE FROM scheduler_cycles"))
        s.execute(text("UPDATE scheduler_lease SET active_cycle_id=NULL, "
                       "heartbeat_at=NULL, owner=NULL WHERE id=1"))
        s.commit()


# ── Config contract ───────────────────────────────────────────────────────────

class TestConfig:
    def test_disabled_by_default(self, monkeypatch):
        for var in ("SCHEDULER_ENABLED", "SCHEDULER_INTERVAL_SECONDS",
                    "SCHEDULER_RUN_ON_STARTUP", "SCHEDULER_STARTUP_CATCHUP"):
            monkeypatch.delenv(var, raising=False)
        cfg = read_scheduler_config()
        assert cfg.enabled is False
        assert cfg.interval_seconds == 300          # the ~5 minute target
        assert cfg.startup_catchup is True
        assert cfg.run_on_startup is False

    def test_overrides(self, monkeypatch):
        monkeypatch.setenv("SCHEDULER_ENABLED", "TRUE")
        monkeypatch.setenv("SCHEDULER_INTERVAL_SECONDS", "60")
        monkeypatch.setenv("SCHEDULER_MAX_RUN_SECONDS", "120")
        cfg = read_scheduler_config()
        assert cfg.enabled is True
        assert cfg.interval_seconds == 60
        assert cfg.max_run_seconds == 120

    def test_invalid_values_fall_back(self, monkeypatch):
        monkeypatch.setenv("SCHEDULER_INTERVAL_SECONDS", "abc")
        monkeypatch.setenv("SCHEDULER_MAX_RUN_SECONDS", "-5")
        cfg = read_scheduler_config()
        assert cfg.interval_seconds == 300
        assert cfg.max_run_seconds == 900

    def test_worker_main_refuses_when_disabled(self, monkeypatch):
        from app.worker import main
        monkeypatch.setenv("SCHEDULER_ENABLED", "false")
        assert main() == 1                          # refuses to loop


# ── Catch-up decision ─────────────────────────────────────────────────────────

def _seed_cycle(session, status, finished_minutes_ago):
    from app.db.orm_models import SchedulerCycleRow
    ts = (datetime.now(tz=timezone.utc)
          - timedelta(minutes=finished_minutes_ago)).isoformat()
    session.add(SchedulerCycleRow(
        id=f"cycle_seed_{status}_{finished_minutes_ago}", trigger="scheduled",
        requested_at=ts, started_at=ts, finished_at=ts, status=status,
    ))
    session.commit()


class TestCatchUp:
    def test_no_history_means_catch_up(self, session):
        assert should_catch_up(session, _cfg(interval_seconds=300)) is True

    def test_fresh_success_means_no_catch_up(self, session):
        _seed_cycle(session, "succeeded", finished_minutes_ago=1)
        assert should_catch_up(session, _cfg(interval_seconds=300)) is False

    def test_stale_success_means_one_catch_up(self, session):
        _seed_cycle(session, "succeeded", finished_minutes_ago=60)
        assert should_catch_up(session, _cfg(interval_seconds=300)) is True

    def test_failures_do_not_count_as_success(self, session):
        _seed_cycle(session, "failed", finished_minutes_ago=1)
        assert should_catch_up(session, _cfg(interval_seconds=300)) is True

    def test_warnings_count_as_success(self, session):
        _seed_cycle(session, "succeeded_with_warnings", finished_minutes_ago=1)
        assert should_catch_up(session, _cfg(interval_seconds=300)) is False


# ── Ticks and the loop ────────────────────────────────────────────────────────

class TestTick:
    def test_tick_runs_a_scheduled_cycle(self, session):
        with patch(RUN_INGESTION, return_value=[_result()]):
            outcome = run_tick(_cfg(), "scheduled")
        assert outcome.status == "succeeded"
        row = session.execute(text(
            "SELECT trigger FROM scheduler_cycles WHERE status='succeeded'"
        )).fetchone()
        assert row[0] == "scheduled"

    def test_tick_coalesces_when_lease_held(self, session):
        from app.ingestion.orchestration import _release_lease, _try_acquire_lease
        _try_acquire_lease(session, "cycle_manual_from_api")
        try:
            with patch(RUN_INGESTION, return_value=[_result()]):
                outcome = run_tick(_cfg(), "scheduled")
            assert outcome.skipped
        finally:
            _release_lease(session, "cycle_manual_from_api")

    def test_loop_runs_catchup_then_ticks_and_beats(self, session):
        stop = threading.Event()
        with patch(RUN_INGESTION, return_value=[_result()]):
            ticks = worker_loop(_cfg(interval_seconds=1), stop, max_ticks=2)
        assert ticks == 2
        # catch-up (no history) + 2 scheduled ticks, all durable:
        triggers = [r[0] for r in session.execute(text(
            "SELECT trigger FROM scheduler_cycles ORDER BY requested_at"
        )).fetchall()]
        assert triggers.count("startup_catchup") == 1
        assert triggers.count("scheduled") == 2
        # heartbeat row exists and reports stopped
        hb = session.execute(text(
            "SELECT state, interval_seconds FROM worker_status WHERE id=1"
        )).fetchone()
        assert hb[0] == "stopped"
        assert hb[1] == 1

    def test_loop_skips_catchup_when_fresh(self, session):
        _seed_cycle(session, "succeeded", finished_minutes_ago=0)
        stop = threading.Event()
        with patch(RUN_INGESTION, return_value=[_result()]):
            worker_loop(_cfg(interval_seconds=1), stop, max_ticks=1)
        triggers = [r[0] for r in session.execute(text(
            "SELECT trigger FROM scheduler_cycles"
        )).fetchall()]
        assert "startup_catchup" not in triggers

    def test_run_on_startup_forces_a_cycle(self, session):
        _seed_cycle(session, "succeeded", finished_minutes_ago=0)   # fresh!
        stop = threading.Event()
        stop.set()                                  # loop body never runs
        with patch(RUN_INGESTION, return_value=[_result()]):
            worker_loop(_cfg(run_on_startup=True), stop)
        triggers = [r[0] for r in session.execute(text(
            "SELECT trigger FROM scheduler_cycles"
        )).fetchall()]
        assert "startup_catchup" in triggers
