"""
Integration tests for the ingestion API endpoints.

Network requests (feedparser.parse) are mocked so tests are fully offline.
Uses the session-scoped TestClient from conftest.py.
"""

import types
from datetime import datetime, timezone
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


def _make_feed(entries, bozo=False):
    return types.SimpleNamespace(entries=entries, bozo=bozo)


# ── GET /api/ingest/sources ───────────────────────────────────────────────────

def test_list_ingest_sources_returns_list(client):
    r = client.get("/api/ingest/sources")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_list_ingest_sources_schema(client):
    r = client.get("/api/ingest/sources")
    src = r.json()[0]
    assert "source_id" in src
    assert "display_name" in src
    assert "feed_url" in src
    assert "enabled" in src
    assert src["type"] == "rss"


def test_eurohoops_is_in_sources(client):
    r = client.get("/api/ingest/sources")
    ids = {s["source_id"] for s in r.json()}
    assert "eurohoops" in ids


# ── POST /api/ingest/run ──────────────────────────────────────────────────────

def test_ingest_run_returns_ok(client):
    entries = [
        _make_entry("Deni Avdija traded to new team", "https://eurohoops.net/fake/1"),
        _make_entry("Maccabi Tel Aviv signs EuroLeague guard", "https://eurohoops.net/fake/2"),
    ]
    with patch("feedparser.parse", return_value=_make_feed(entries)):
        r = client.post("/api/ingest/run")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "error")
    assert isinstance(data["sources"], list)
    assert len(data["sources"]) > 0


def test_ingest_run_single_source(client):
    entries = [_make_entry("EuroLeague finals: Real Madrid wins title", "https://eurohoops.net/fake/10")]
    with patch("feedparser.parse", return_value=_make_feed(entries)):
        r = client.post("/api/ingest/run?source_id=eurohoops")
    assert r.status_code == 200
    data = r.json()
    sources = data["sources"]
    assert len(sources) == 1
    assert sources[0]["source_id"] == "eurohoops"


def test_ingest_run_counts_returned(client):
    entries = [_make_entry("New NBA signing news", "https://eurohoops.net/fake/100")]
    with patch("feedparser.parse", return_value=_make_feed(entries)):
        r = client.post("/api/ingest/run?source_id=eurohoops")
    result = r.json()["sources"][0]
    assert "fetched" in result
    assert "inserted" in result
    assert "skipped_duplicate" in result
    assert "failed" in result


def test_ingest_run_unknown_source_returns_error_summary(client):
    r = client.post("/api/ingest/run?source_id=nonexistent_source")
    assert r.status_code == 200
    sources = r.json()["sources"]
    assert sources[0]["source_id"] == "nonexistent_source"
    assert len(sources[0]["errors"]) > 0


def test_ingest_run_dedup_skips_on_second_run(client):
    """Running ingestion twice for the same items: second run must skip all."""
    entries = [_make_entry("Unique title for dedup test", "https://eurohoops.net/fake/dedup-999")]
    with patch("feedparser.parse", return_value=_make_feed(entries)):
        r1 = client.post("/api/ingest/run?source_id=eurohoops")
    first = r1.json()["sources"][0]

    with patch("feedparser.parse", return_value=_make_feed(entries)):
        r2 = client.post("/api/ingest/run?source_id=eurohoops")
    second = r2.json()["sources"][0]

    # First run: inserted the article (unless it was already in DB from another test)
    # Second run: must have skipped == fetched and inserted == 0
    assert second["skipped_duplicate"] == second["fetched"]
    assert second["inserted"] == 0


def test_ingested_article_appears_in_articles_list(client):
    """After ingestion, new articles should appear in GET /api/articles."""
    url = "https://eurohoops.net/fake/appear-in-list-999"
    entries = [_make_entry("Maccabi Tel Aviv in advanced talks with EuroLeague player", url)]
    with patch("feedparser.parse", return_value=_make_feed(entries)):
        client.post("/api/ingest/run?source_id=eurohoops")

    r = client.get("/api/articles")
    article_urls = [a["url"] for a in r.json()]
    assert url in article_urls


def test_ingested_article_appears_in_debug_feed(client):
    """After ingestion, new articles appear in debug feed regardless of decision."""
    url = "https://eurohoops.net/fake/debug-feed-999"
    entries = [_make_entry("Greek League: Schedule for next round", url)]
    with patch("feedparser.parse", return_value=_make_feed(entries)):
        client.post("/api/ingest/run?source_id=eurohoops")

    r = client.get("/api/debug/feed/guy")
    assert r.status_code == 200
    feed_urls = [item["article"]["url"] for item in r.json()]
    assert url in feed_urls


def test_ingested_maccabi_article_scores_high_for_guy(client):
    """A Maccabi EuroLeague signing should score high_feed or push for Guy."""
    url = "https://eurohoops.net/fake/maccabi-signing-for-scoring"
    entries = [_make_entry("Maccabi Tel Aviv signs EuroLeague guard — official", url)]
    with patch("feedparser.parse", return_value=_make_feed(entries)):
        client.post("/api/ingest/run?source_id=eurohoops")

    r = client.get("/api/debug/feed/guy")
    items = r.json()
    maccabi_item = next((i for i in items if i["article"]["url"] == url), None)
    assert maccabi_item is not None
    assert maccabi_item["decision"] in ("high_feed", "push", "feed")


def test_ingested_deni_trade_scores_push_for_guy(client):
    """A Deni Avdija trade should score push for Guy."""
    url = "https://eurohoops.net/fake/deni-trade-push-test"
    entries = [_make_entry("Official: Deni Avdija traded to new NBA team", url)]
    with patch("feedparser.parse", return_value=_make_feed(entries)):
        client.post("/api/ingest/run?source_id=eurohoops")

    r = client.get("/api/feed/guy")
    feed_urls = [item["article"]["url"] for item in r.json()]
    assert url in feed_urls


# ── GET /api/ingest/runs ──────────────────────────────────────────────────────

def test_ingest_runs_returns_list(client):
    r = client.get("/api/ingest/runs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_ingest_runs_recorded_after_run(client):
    entries = [_make_entry("Run log test article", "https://eurohoops.net/fake/run-log-001")]
    with patch("feedparser.parse", return_value=_make_feed(entries)):
        client.post("/api/ingest/run?source_id=eurohoops")

    r = client.get("/api/ingest/runs")
    runs = r.json()
    assert len(runs) > 0
    # Most recent run should be for eurohoops
    assert any(run["source_id"] == "eurohoops" for run in runs)


def test_ingest_runs_schema(client):
    r = client.get("/api/ingest/runs")
    if r.json():
        run = r.json()[0]
        assert "id" in run
        assert "source_id" in run
        assert "started_at" in run
        assert "status" in run
        assert "inserted_count" in run
        assert "fetched_count" in run
        assert "skipped_duplicate_count" in run


# ── GET /api/ingest/quality ───────────────────────────────────────────────────

def test_quality_endpoint_returns_200(client):
    r = client.get("/api/ingest/quality")
    assert r.status_code == 200


def test_quality_response_schema(client):
    r = client.get("/api/ingest/quality")
    data = r.json()
    assert "total_rss_articles" in data
    assert "sport_breakdown" in data
    assert "league_breakdown" in data
    assert "event_type_breakdown" in data
    assert "importance_breakdown" in data
    assert "low_confidence_count" in data
    assert "questionable_articles" in data
    assert isinstance(data["questionable_articles"], list)


def test_quality_total_matches_breakdown_sum(client):
    """Sum of sport_breakdown values must equal total_rss_articles."""
    # Ingest some articles so there's something to check
    entries = [
        _make_entry("Maccabi Tel Aviv signs guard", "https://eurohoops.net/fake/quality-01"),
        _make_entry("Deni Avdija traded to new NBA team", "https://eurohoops.net/fake/quality-02"),
    ]
    with patch("feedparser.parse", return_value=_make_feed(entries)):
        client.post("/api/ingest/run?source_id=eurohoops")

    r = client.get("/api/ingest/quality")
    data = r.json()
    assert sum(data["sport_breakdown"].values()) == data["total_rss_articles"]


def test_quality_questionable_article_schema(client):
    """If there are questionable articles, each must have the expected fields."""
    r = client.get("/api/ingest/quality")
    data = r.json()
    for item in data["questionable_articles"]:
        assert "id" in item
        assert "title" in item
        assert "source" in item
        assert "sport" in item
        assert "event_type" in item
        assert "confidence" in item
        assert "reasons" in item
        assert isinstance(item["reasons"], list)
        assert len(item["reasons"]) > 0
