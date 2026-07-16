"""
PR 13 — scheduler unit tests (no sleeps, no async loop execution).

Covers:
- _read_scheduler_env defaults + overrides + invalid values
- run_ingestion_guarded: happy path, error path, busy-lock path, lock release
- start_scheduler returns None when disabled (default)
"""

import types
from unittest.mock import patch

import pytest

from app.ingestion.scheduler import (
    SchedulerState,
    _read_scheduler_env,
    run_ingestion_guarded,
    start_scheduler,
)


# ── Env parsing ───────────────────────────────────────────────────────────────

class TestReadSchedulerEnv:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("INGESTION_SCHEDULER_ENABLED", raising=False)
        monkeypatch.delenv("INGESTION_SCHEDULER_INTERVAL_MINUTES", raising=False)
        monkeypatch.delenv("INGESTION_SCHEDULER_INITIAL_DELAY_SECONDS", raising=False)
        enabled, interval, delay = _read_scheduler_env()
        assert enabled is False
        assert interval == 15
        assert delay == 30

    def test_enabled_true(self, monkeypatch):
        monkeypatch.setenv("INGESTION_SCHEDULER_ENABLED", "true")
        enabled, _, _ = _read_scheduler_env()
        assert enabled is True

    def test_enabled_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("INGESTION_SCHEDULER_ENABLED", "TRUE")
        enabled, _, _ = _read_scheduler_env()
        assert enabled is True

    def test_custom_interval_and_delay(self, monkeypatch):
        monkeypatch.setenv("INGESTION_SCHEDULER_INTERVAL_MINUTES", "5")
        monkeypatch.setenv("INGESTION_SCHEDULER_INITIAL_DELAY_SECONDS", "0")
        _, interval, delay = _read_scheduler_env()
        assert interval == 5
        assert delay == 0

    def test_invalid_values_fall_back_to_defaults(self, monkeypatch):
        monkeypatch.setenv("INGESTION_SCHEDULER_INTERVAL_MINUTES", "abc")
        monkeypatch.setenv("INGESTION_SCHEDULER_INITIAL_DELAY_SECONDS", "-5")
        _, interval, delay = _read_scheduler_env()
        assert interval == 15
        assert delay == 30

    def test_zero_interval_falls_back(self, monkeypatch):
        monkeypatch.setenv("INGESTION_SCHEDULER_INTERVAL_MINUTES", "0")
        _, interval, _ = _read_scheduler_env()
        assert interval == 15


# ── run_ingestion_guarded ─────────────────────────────────────────────────────

def _fake_result(source_id="walla_sport", inserted=3):
    return types.SimpleNamespace(
        source_id=source_id,
        fetched=5,
        inserted=inserted,
        skipped_duplicate=2,
        skipped_filtered=0,
        failed=0,
        errors=[],
    )


def _hold_lease(cycle_id="cycle_test_holder"):
    """Hold the DURABLE single-flight lease (M7-1, #147) — the guard is the
    database lease now, not the process-local lock."""
    from app.db.database import SessionLocal
    from app.ingestion.orchestration import _try_acquire_lease
    with SessionLocal() as s:
        acquired, _ = _try_acquire_lease(s, cycle_id)
        assert acquired
    return cycle_id


def _free_lease(cycle_id):
    from app.db.database import SessionLocal
    from app.ingestion.orchestration import _release_lease
    with SessionLocal() as s:
        _release_lease(s, cycle_id)


RUN_INGESTION = "app.ingestion.ingestion_service.run_ingestion"


class TestRunIngestionGuarded:
    def test_happy_path_updates_state_and_returns_summary(self, client):
        state = SchedulerState()
        with patch(RUN_INGESTION, return_value=[_fake_result()]):
            summary = run_ingestion_guarded(state, trigger="run_now")

        assert summary == [{
            "source_id": "walla_sport",
            "fetched": 5,
            "inserted": 3,
            "skipped_duplicate": 2,
            "skipped_filtered": 0,
            "failed": 0,
        }]
        assert state.last_status == "ok"
        assert state.last_error is None
        assert state.last_started_at is not None
        assert state.last_finished_at is not None

    def test_error_path_sets_error_status_and_releases_guard(self, client):
        from app.db.database import SessionLocal
        from app.ingestion.orchestration import current_lease
        state = SchedulerState()
        with patch(RUN_INGESTION, side_effect=RuntimeError("boom")):
            summary = run_ingestion_guarded(state, trigger="scheduled")

        assert summary == []
        assert state.last_status == "error"
        assert "boom" in state.last_error
        with SessionLocal() as s:
            assert current_lease(s) is None      # the DURABLE guard was released

    def test_busy_guard_returns_none(self, client):
        state = SchedulerState()
        holder = _hold_lease()
        try:
            summary = run_ingestion_guarded(state, trigger="run_now")
            assert summary is None
            # State untouched except nothing started
            assert state.last_started_at is None
        finally:
            _free_lease(holder)

    def test_busy_guard_scheduled_tick_marks_skipped(self, client):
        state = SchedulerState()
        holder = _hold_lease()
        try:
            summary = run_ingestion_guarded(state, trigger="scheduled")
            assert summary is None
            assert state.last_status == "skipped"
        finally:
            _free_lease(holder)

    def test_source_id_forwarded(self, client):
        state = SchedulerState()
        with patch(RUN_INGESTION, return_value=[_fake_result("sport5_sport")]) as mock_run:
            run_ingestion_guarded(state, trigger="run_now", source_id="sport5_sport")
        assert mock_run.call_args.kwargs.get("source_id") == "sport5_sport"


# ── start_scheduler ───────────────────────────────────────────────────────────

class TestStartScheduler:
    def test_disabled_by_default_returns_none(self, monkeypatch):
        monkeypatch.delenv("INGESTION_SCHEDULER_ENABLED", raising=False)
        state = SchedulerState()
        task = start_scheduler(state)
        assert task is None
        assert state.enabled is False
        assert state.running is False

    def test_disabled_explicit_false(self, monkeypatch):
        monkeypatch.setenv("INGESTION_SCHEDULER_ENABLED", "false")
        state = SchedulerState()
        assert start_scheduler(state) is None

    def test_interval_recorded_even_when_disabled(self, monkeypatch):
        monkeypatch.setenv("INGESTION_SCHEDULER_ENABLED", "false")
        monkeypatch.setenv("INGESTION_SCHEDULER_INTERVAL_MINUTES", "7")
        state = SchedulerState()
        start_scheduler(state)
        assert state.interval_minutes == 7
