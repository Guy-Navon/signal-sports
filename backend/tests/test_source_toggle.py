"""
PR 13.1 — runtime source enable/disable override tests.

The Sources page toggle calls PATCH /api/ingest/sources/{source_id}; the
override is persisted in source_overrides, wins over the config.py default,
and is respected by GET sources, source health, and run-all ingestion.

Every test restores the default (clears the override) in a finally block —
the DB is shared across the session-scoped TestClient.
"""

import types
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.db.database import SessionLocal
from app.repositories import source_override_repository


@contextmanager
def override_cleared_after(*source_ids):
    try:
        yield
    finally:
        with SessionLocal() as session:
            for source_id in source_ids:
                source_override_repository.clear_override(session, source_id)


def _source(client, source_id):
    return next(
        s for s in client.get("/api/ingest/sources").json()
        if s["source_id"] == source_id
    )


def _health(client, source_id):
    return next(
        s for s in client.get("/api/ingest/source-health").json()
        if s["source_id"] == source_id
    )


class TestToggleEndpoint:
    def test_enable_sport5_reflected_everywhere(self, client):
        with override_cleared_after("sport5_sport"):
            r = client.patch("/api/ingest/sources/sport5_sport", json={"enabled": True})
            assert r.status_code == 200
            body = r.json()
            assert body["source_id"] == "sport5_sport"
            assert body["enabled"] is True
            assert body["is_pilot"] is True
            assert body["type"] == "html_scrape"

            # GET sources reflects the override
            assert _source(client, "sport5_sport")["enabled"] is True
            # Source health no longer reports "disabled"
            assert _health(client, "sport5_sport")["freshness"] != "disabled"

    def test_disable_walla_reflected(self, client):
        with override_cleared_after("walla_sport"):
            r = client.patch("/api/ingest/sources/walla_sport", json={"enabled": False})
            assert r.status_code == 200
            assert _source(client, "walla_sport")["enabled"] is False
            assert _health(client, "walla_sport")["freshness"] == "disabled"

    def test_clearing_override_restores_config_default(self, client):
        with override_cleared_after("sport5_sport"):
            client.patch("/api/ingest/sources/sport5_sport", json={"enabled": True})
        # override cleared → back to config default (disabled)
        assert _source(client, "sport5_sport")["enabled"] is False

    def test_unknown_source_returns_404(self, client):
        r = client.patch("/api/ingest/sources/nonexistent", json={"enabled": True})
        assert r.status_code == 404

    def test_toggle_is_idempotent_upsert(self, client):
        with override_cleared_after("sport5_sport"):
            client.patch("/api/ingest/sources/sport5_sport", json={"enabled": True})
            client.patch("/api/ingest/sources/sport5_sport", json={"enabled": False})
            r = client.patch("/api/ingest/sources/sport5_sport", json={"enabled": True})
            assert r.json()["enabled"] is True
            assert _source(client, "sport5_sport")["enabled"] is True

    def test_override_persisted_in_db(self, client):
        with override_cleared_after("sport5_sport"):
            client.patch("/api/ingest/sources/sport5_sport", json={"enabled": True})
            with SessionLocal() as session:
                assert source_override_repository.get_override(
                    session, "sport5_sport"
                ) is True


class TestRunAllRespectsOverride:
    def _make_feed(self):
        return types.SimpleNamespace(entries=[], bozo=False)

    def _fixture_response(self):
        import pathlib
        html = (pathlib.Path(__file__).parent / "fixtures" / "sport5_category.html"
                ).read_text(encoding="utf-8")
        resp = MagicMock()
        resp.text = html
        resp.raise_for_status = MagicMock()
        return resp

    def test_run_all_includes_sport5_when_enabled(self, client):
        with override_cleared_after("sport5_sport"):
            client.patch("/api/ingest/sources/sport5_sport", json={"enabled": True})
            with patch("feedparser.parse", return_value=self._make_feed()), \
                 patch("app.ingestion.adapters.sport5_adapter.httpx.get",
                       return_value=self._fixture_response()):
                r = client.post("/api/ingest/run")
            source_ids = [s["source_id"] for s in r.json()["sources"]]
            assert "sport5_sport" in source_ids

    def test_run_all_excludes_sport5_by_default(self, client):
        with patch("feedparser.parse", return_value=self._make_feed()):
            r = client.post("/api/ingest/run")
        source_ids = [s["source_id"] for s in r.json()["sources"]]
        assert "sport5_sport" not in source_ids

    def test_run_all_excludes_disabled_walla(self, client):
        with override_cleared_after("walla_sport"):
            client.patch("/api/ingest/sources/walla_sport", json={"enabled": False})
            with patch("feedparser.parse", return_value=self._make_feed()):
                r = client.post("/api/ingest/run")
            source_ids = [s["source_id"] for s in r.json()["sources"]]
            assert "walla_sport" not in source_ids
            assert "israel_hayom_sport" in source_ids
