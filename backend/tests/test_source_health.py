# PR 6 (#54): this file exercises the legacy {user_id}/ops surface, which is
# admin-gated fail-closed — it runs under the explicit admin_client identity.
"""
PR 13 — source-health endpoint tests.

_freshness() is unit-tested directly for all five states; the endpoint is
tested for shape, disabled sources, error/healthy transitions, and
consecutive-failure counting using records inserted via the repository.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api.routes_ingest import _freshness
from app.db.database import SessionLocal
from app.models.ingestion import IngestionRunRecord
from app.repositories import ingestion_repository


def _record(source_id: str, status: str = "ok", minutes_ago: float = 0,
            error_message: str | None = None) -> IngestionRunRecord:
    started = datetime.now(tz=timezone.utc) - timedelta(minutes=minutes_ago)
    return IngestionRunRecord(
        id=f"test_health_{uuid.uuid4().hex[:12]}",
        source_id=source_id,
        started_at=started,
        finished_at=started,
        status=status,
        fetched_count=10,
        inserted_count=4,
        skipped_duplicate_count=6,
        failed_count=1 if status == "error" else 0,
        error_message=error_message,
    )


# ── _freshness pure function ──────────────────────────────────────────────────

class TestFreshness:
    NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)

    def test_disabled_wins_over_everything(self):
        run = _record("x", status="error")
        assert _freshness(False, run, 15, self.NOW) == "disabled"
        assert _freshness(False, None, 15, self.NOW) == "disabled"

    def test_never_run(self):
        assert _freshness(True, None, 15, self.NOW) == "never_run"

    def test_error_when_latest_run_failed(self):
        run = _record("x", status="error")
        run.started_at = self.NOW - timedelta(minutes=1)
        assert _freshness(True, run, 15, self.NOW) == "error"

    def test_healthy_within_2x_interval(self):
        run = _record("x", status="ok")
        run.started_at = self.NOW - timedelta(minutes=29)
        assert _freshness(True, run, 15, self.NOW) == "healthy"

    def test_stale_beyond_2x_interval(self):
        run = _record("x", status="ok")
        run.started_at = self.NOW - timedelta(minutes=31)
        assert _freshness(True, run, 15, self.NOW) == "stale"


# ── Endpoint ──────────────────────────────────────────────────────────────────

class TestSourceHealthEndpoint:
    def _health(self, admin_client, source_id: str) -> dict:
        r = admin_client.get("/api/ingest/source-health")
        assert r.status_code == 200
        return next(s for s in r.json() if s["source_id"] == source_id)

    def test_all_configured_sources_present_with_stable_shape(self, admin_client):
        r = admin_client.get("/api/ingest/source-health")
        body = r.json()
        source_ids = {s["source_id"] for s in body}
        assert {"walla_sport", "israel_hayom_sport", "ynet_sport", "one_sport",
                "eurohoops", "sportando", "sport5_sport"} <= source_ids
        for s in body:
            for key in (
                "source_id", "display_name", "enabled", "source_type", "is_pilot",
                "freshness", "last_run_at", "last_status", "last_fetched_count",
                "last_inserted_count", "last_failed_count",
                "last_skipped_duplicate_count", "consecutive_failures",
                "last_error_message",
            ):
                assert key in s, f"missing {key} for {s['source_id']}"

    def test_disabled_sources_report_disabled(self, admin_client):
        for source_id in ("eurohoops", "sportando", "sport5_sport"):
            assert self._health(admin_client, source_id)["freshness"] == "disabled"

    def test_sport5_metadata(self, admin_client):
        sport5 = self._health(admin_client, "sport5_sport")
        assert sport5["source_type"] == "html_scrape"
        assert sport5["is_pilot"] is True
        assert sport5["enabled"] is False

    def test_error_freshness_and_consecutive_failures(self, admin_client):
        # Negative minutes_ago = slightly in the future, guaranteeing these are
        # the newest runs for the source even though other tests in the shared
        # session insert run records of their own.
        with SessionLocal() as session:
            ingestion_repository.insert(session, _record(
                "israel_hayom_sport", status="error", minutes_ago=-1,
                error_message="fetch failed"))
            ingestion_repository.insert(session, _record(
                "israel_hayom_sport", status="error", minutes_ago=-2,
                error_message="fetch failed again"))

        health = self._health(admin_client, "israel_hayom_sport")
        assert health["freshness"] == "error"
        assert health["consecutive_failures"] >= 2
        assert health["last_status"] == "error"
        assert health["last_error_message"] == "fetch failed again"

    def test_ok_run_resets_to_healthy_and_zero_failures(self, admin_client):
        with SessionLocal() as session:
            ingestion_repository.insert(session, _record(
                "israel_hayom_sport", status="ok", minutes_ago=-3))

        health = self._health(admin_client, "israel_hayom_sport")
        assert health["freshness"] == "healthy"
        assert health["consecutive_failures"] == 0
        assert health["last_status"] == "ok"
        assert health["last_fetched_count"] == 10
        assert health["last_inserted_count"] == 4
        assert health["last_skipped_duplicate_count"] == 6
