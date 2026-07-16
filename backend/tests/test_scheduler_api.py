# PR 6 (#54): this file exercises the legacy {user_id}/ops surface, which is
# admin-gated fail-closed — it runs under the explicit admin_client identity.
"""
PR 13 — scheduler/lock API tests.

Covers:
- GET /api/ingest/scheduler/status stable shape + defaults
- POST /api/ingest/scheduler/run-now runs ingestion via the service path
- 409 conflict for run-now AND POST /api/ingest/run while the lock is held
- Lock is released after runs (subsequent calls succeed)
"""

import types
from unittest.mock import patch

import pytest


def _make_entry(title: str, link: str):
    return types.SimpleNamespace(
        title=title, link=link,
        published_parsed=None, updated_parsed=None, summary=None,
    )


def _make_feed(entries):
    return types.SimpleNamespace(entries=entries, bozo=False)


class TestSchedulerStatusEndpoint:
    def test_status_shape_and_defaults(self, admin_client):
        r = admin_client.get("/api/ingest/scheduler/status")
        assert r.status_code == 200
        body = r.json()
        # Stable shape — every field present
        for key in (
            "enabled", "running", "interval_minutes", "next_run_at",
            "last_started_at", "last_finished_at", "last_status",
            "last_error", "active_run", "last_result_summary",
        ):
            assert key in body
        # Scheduler is disabled by default in the test environment
        assert body["enabled"] is False
        assert body["running"] is False
        assert body["active_run"] is None
        assert isinstance(body["interval_minutes"], int)


class TestRunNowEndpoint:
    def test_run_now_executes_ingestion(self, admin_client):
        entries = [_make_entry("NBA: משחק ניקס", "https://walla.co.il/fake/sched1")]
        with patch("feedparser.parse", return_value=_make_feed(entries)), \
             patch("app.ingestion.adapters.sport5_adapter.httpx.get",
                   side_effect=AssertionError("sport5 disabled — must not be fetched")):
            r = admin_client.post("/api/ingest/scheduler/run-now")
        assert r.status_code == 200
        body = r.json()
        assert body["trigger"] == "run_now"
        assert body["status"] == "ok"
        source_ids = [s["source_id"] for s in body["sources"]]
        assert "walla_sport" in source_ids
        assert "sport5_sport" not in source_ids  # disabled pilot excluded

    def test_run_now_conflict_while_guard_held(self, admin_client):
        # The guard is the DURABLE lease (M7-1, #147) — hold it the way another
        # PROCESS (the scheduler worker) would, and both endpoints must 409.
        from app.db.database import SessionLocal
        from app.ingestion.orchestration import _release_lease, _try_acquire_lease
        with SessionLocal() as s:
            acquired, _ = _try_acquire_lease(s, "cycle_other_process")
            assert acquired
        try:
            r = admin_client.post("/api/ingest/scheduler/run-now")
            assert r.status_code == 409
            detail = r.json()["detail"]
            assert detail["error"] == "ingestion_already_running"
            assert "message" in detail
            assert detail["active_run"]["cycle_id"] == "cycle_other_process"
        finally:
            with SessionLocal() as s:
                _release_lease(s, "cycle_other_process")

    def test_manual_run_conflict_while_guard_held(self, admin_client):
        from app.db.database import SessionLocal
        from app.ingestion.orchestration import _release_lease, _try_acquire_lease
        with SessionLocal() as s:
            acquired, _ = _try_acquire_lease(s, "cycle_other_process")
            assert acquired
        try:
            r = admin_client.post("/api/ingest/run?source_id=walla_sport")
            assert r.status_code == 409
            assert r.json()["detail"]["error"] == "ingestion_already_running"
        finally:
            with SessionLocal() as s:
                _release_lease(s, "cycle_other_process")

    def test_lock_released_after_runs(self, admin_client):
        """Manual run then run-now both succeed — the lock never leaks."""
        entries = [_make_entry("NBA: עוד משחק", "https://walla.co.il/fake/sched2")]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            first = admin_client.post("/api/ingest/run?source_id=walla_sport")
            second = admin_client.post("/api/ingest/scheduler/run-now")
        assert first.status_code == 200
        assert second.status_code == 200

    def test_status_reflects_last_run(self, admin_client):
        entries = [_make_entry("NBA: משחק שלישי", "https://walla.co.il/fake/sched3")]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            admin_client.post("/api/ingest/scheduler/run-now")
        body = admin_client.get("/api/ingest/scheduler/status").json()
        assert body["last_status"] == "ok"
        assert body["last_started_at"] is not None
        assert body["last_finished_at"] is not None
        assert body["active_run"] is None
        assert isinstance(body["last_result_summary"], list)
