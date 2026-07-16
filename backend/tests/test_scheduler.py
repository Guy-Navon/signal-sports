"""
Legacy scheduler shim tests (PR 13 → M7-2, #148).

The in-process loop and its INGESTION_SCHEDULER_* env vars were retired by
#148 (the dedicated worker owns cadence — see test_worker_148.py). What
remains under test here is the shim contract: run_ingestion_guarded delegates
to the canonical orchestration and keeps the legacy in-memory status mirror
coherent until M7-4 replaces that endpoint.
"""

import types
from unittest.mock import patch

import pytest

from app.ingestion.scheduler import (
    SchedulerState,
    run_ingestion_guarded,
)


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


# ── The retirement itself is contract (M7-2, #148) ───────────────────────────

class TestInProcessSchedulerIsRetired:
    def test_no_loop_starters_exist(self):
        """A second polling loop must be impossible by construction: the API
        process exposes NO way to start one. The worker process is the only
        thing that polls."""
        import app.ingestion.scheduler as scheduler_module
        assert not hasattr(scheduler_module, "start_scheduler")
        assert not hasattr(scheduler_module, "stop_scheduler")
        assert not hasattr(scheduler_module, "_scheduler_loop")

    def test_app_lifespan_does_not_reference_a_scheduler(self):
        import inspect

        import app.main as main_module
        source = inspect.getsource(main_module)
        assert "start_scheduler" not in source
