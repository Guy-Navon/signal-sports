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

from app.ingestion.scheduler import scheduler_state


def _make_entry(title: str, link: str):
    return types.SimpleNamespace(
        title=title, link=link,
        published_parsed=None, updated_parsed=None, summary=None,
    )


def _make_feed(entries):
    return types.SimpleNamespace(entries=entries, bozo=False)


class TestSchedulerStatusEndpoint:
    def test_status_shape_and_defaults(self, client):
        r = client.get("/api/ingest/scheduler/status")
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
    def test_run_now_executes_ingestion(self, client):
        entries = [_make_entry("NBA: משחק ניקס", "https://walla.co.il/fake/sched1")]
        with patch("feedparser.parse", return_value=_make_feed(entries)), \
             patch("app.ingestion.adapters.sport5_adapter.httpx.get",
                   side_effect=AssertionError("sport5 disabled — must not be fetched")):
            r = client.post("/api/ingest/scheduler/run-now")
        assert r.status_code == 200
        body = r.json()
        assert body["trigger"] == "run_now"
        assert body["status"] == "ok"
        source_ids = [s["source_id"] for s in body["sources"]]
        assert "walla_sport" in source_ids
        assert "sport5_sport" not in source_ids  # disabled pilot excluded

    def test_run_now_conflict_while_lock_held(self, client):
        acquired = scheduler_state.lock.acquire(blocking=False)
        assert acquired
        try:
            r = client.post("/api/ingest/scheduler/run-now")
            assert r.status_code == 409
            detail = r.json()["detail"]
            assert detail["error"] == "ingestion_already_running"
            assert "message" in detail
        finally:
            scheduler_state.lock.release()

    def test_manual_run_conflict_while_lock_held(self, client):
        acquired = scheduler_state.lock.acquire(blocking=False)
        assert acquired
        try:
            r = client.post("/api/ingest/run?source_id=walla_sport")
            assert r.status_code == 409
            assert r.json()["detail"]["error"] == "ingestion_already_running"
        finally:
            scheduler_state.lock.release()

    def test_lock_released_after_runs(self, client):
        """Manual run then run-now both succeed — the lock never leaks."""
        entries = [_make_entry("NBA: עוד משחק", "https://walla.co.il/fake/sched2")]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            first = client.post("/api/ingest/run?source_id=walla_sport")
            second = client.post("/api/ingest/scheduler/run-now")
        assert first.status_code == 200
        assert second.status_code == 200

    def test_status_reflects_last_run(self, client):
        entries = [_make_entry("NBA: משחק שלישי", "https://walla.co.il/fake/sched3")]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            client.post("/api/ingest/scheduler/run-now")
        body = client.get("/api/ingest/scheduler/status").json()
        assert body["last_status"] == "ok"
        assert body["last_started_at"] is not None
        assert body["last_finished_at"] is not None
        assert body["active_run"] is None
        assert isinstance(body["last_result_summary"], list)
