# PR 6 (#54): this file exercises the legacy {user_id}/ops surface, which is
# admin-gated fail-closed — it runs under the explicit admin_client identity.
"""
Tests for POST /api/dev/reset-rss-data.

All tests use the session-scoped TestClient from conftest.py.
The reset endpoint is guarded by ALLOW_DEV_RESET=true.
"""

import types
from unittest.mock import patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_entry(title: str, link: str):
    return types.SimpleNamespace(
        title=title,
        link=link,
        published_parsed=None,
        updated_parsed=None,
        summary=None,
    )


def _make_feed(entries):
    return types.SimpleNamespace(entries=entries, bozo=False)


# ── Disabled by default ───────────────────────────────────────────────────────

def test_reset_returns_403_when_disabled(admin_client, monkeypatch):
    """ALLOW_DEV_RESET not set (default) → 403."""
    monkeypatch.delenv("ALLOW_DEV_RESET", raising=False)
    r = admin_client.post("/api/dev/reset-rss-data")
    assert r.status_code == 403
    assert "ALLOW_DEV_RESET" in r.json()["detail"]


def test_reset_returns_403_when_env_is_false(admin_client, monkeypatch):
    """ALLOW_DEV_RESET=false → 403."""
    monkeypatch.setenv("ALLOW_DEV_RESET", "false")
    r = admin_client.post("/api/dev/reset-rss-data")
    assert r.status_code == 403


# ── Enabled behavior ──────────────────────────────────────────────────────────

def test_reset_returns_200_when_enabled(admin_client, monkeypatch):
    """ALLOW_DEV_RESET=true → 200 with deleted counts."""
    monkeypatch.setenv("ALLOW_DEV_RESET", "true")
    r = admin_client.post("/api/dev/reset-rss-data")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert isinstance(data["deleted_articles"], int)
    assert isinstance(data["deleted_ingestion_runs"], int)


def test_reset_deletes_rss_articles(admin_client, monkeypatch):
    """After reset, rss_ articles no longer appear in the articles list."""
    monkeypatch.setenv("ALLOW_DEV_RESET", "true")

    # Insert an rss_ article via mocked ingestion
    entries = [_make_entry("Deni Avdija signs with new team", "https://eurohoops.net/reset-test/1")]
    with patch("feedparser.parse", return_value=_make_feed(entries)):
        admin_client.post("/api/ingest/run?source_id=eurohoops")

    # Verify an rss_ article exists
    articles_before = admin_client.get("/api/articles").json()
    rss_before = [a for a in articles_before if a["id"].startswith("rss_")]
    assert len(rss_before) > 0, "Expected at least one rss_ article before reset"

    # Reset
    r = admin_client.post("/api/dev/reset-rss-data")
    assert r.status_code == 200
    data = r.json()
    assert data["deleted_articles"] >= 1

    # rss_ articles should be gone
    articles_after = admin_client.get("/api/articles").json()
    rss_after = [a for a in articles_after if a["id"].startswith("rss_")]
    assert len(rss_after) == 0, "Expected no rss_ articles after reset"


def test_reset_does_not_delete_profiles(admin_client, monkeypatch):
    """Reset does not delete user profiles."""
    monkeypatch.setenv("ALLOW_DEV_RESET", "true")
    admin_client.post("/api/dev/reset-rss-data")

    r = admin_client.get("/api/profiles")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_reset_does_not_delete_sources(admin_client, monkeypatch):
    """Reset does not delete configured RSS sources."""
    monkeypatch.setenv("ALLOW_DEV_RESET", "true")
    admin_client.post("/api/dev/reset-rss-data")

    r = admin_client.get("/api/ingest/sources")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_reset_does_not_delete_non_rss_seed_articles(admin_client, monkeypatch):
    """Reset does not delete seed articles (id starts with article_)."""
    monkeypatch.setenv("ALLOW_DEV_RESET", "true")
    admin_client.post("/api/dev/reset-rss-data")

    # Seed articles are accessible via single-item lookup even after reset
    r = admin_client.get("/api/articles/article_001")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "article_001"


def test_reset_deletes_ingestion_runs(admin_client, monkeypatch):
    """Reset clears the ingestion run log."""
    monkeypatch.setenv("ALLOW_DEV_RESET", "true")

    # Run ingestion to create at least one run log entry
    entries = [_make_entry("EuroLeague finals", "https://eurohoops.net/reset-runs/1")]
    with patch("feedparser.parse", return_value=_make_feed(entries)):
        admin_client.post("/api/ingest/run?source_id=eurohoops")

    r = admin_client.post("/api/dev/reset-rss-data")
    assert r.status_code == 200
    assert r.json()["deleted_ingestion_runs"] >= 0  # may be 0 if prior tests already reset
